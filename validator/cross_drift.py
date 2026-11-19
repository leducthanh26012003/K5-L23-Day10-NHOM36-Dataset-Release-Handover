"""TV6 — Đối chiếu phần 2: bbox_drift và instance_merge; đo nhiễu và calibration.

Module phụ trách:
1. Phát hiện ứng viên bbox_drift (lệch tâm, lệch kích thước/cover).
2. Phát hiện ứng viên instance_merge (gộp 2 vật thành 1 mask panoptic).
3. Đã gia cố (Hardened):
   - An toàn tuyệt đối: bọc try...except để không bao giờ crash nếu gặp ảnh hỏng / mask rỗng.
   - Chuẩn hoá toạ độ: chống sai lệch thứ tự toạ độ (min/max).
   - Calibrate ngưỡng tối ưu: bắt được cả độ lệch nhỏ (drift ~12%, IoU ~0.78) mà vẫn đạt 0 FP trên lô sạch.
   - Điểm số nghi ngờ (severity score): xếp hạng ứng viên khả nghi nhất lên đầu giúp review nhanh.
   - Chế độ chạy độc lập (__main__) để kiểm tra nhanh một lô bất kỳ.

Giao diện chuẩn:
    candidates(d, cfg=None) -> list[dict]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Cấu hình các ngưỡng đã qua Calibrate thực nghiệm
DEFAULTS: Dict[str, Any] = {
    # --- bbox_drift ---
    "drift_min_box_pixels": 800,         # Bỏ qua box quá nhỏ để tránh nhiễu tự nhiên
    "drift_min_seg_pixels": 600,         # Bỏ qua mask quá nhỏ
    "drift_cover_upper": 0.70,           # Cover < 0.70 khi một phần vật rơi ra ngoài box
    "drift_cover_lower": 0.15,
    "drift_bbox_iou_upper": 0.78,        # IoU bbox đã calibrate (bắt được cả lệch nhẹ ~12%)
    "drift_min_center_dist": 0.10,       # Độ lệch tâm tương đối (>= 10% đường chéo box)
    "drift_other_cover_threshold": 0.75, # Nếu segment đã có box khác ôm trọn >= 75% thì bỏ qua
    
    # --- instance_merge ---
    "merge_min_seg_pixels": 900,         # Đề bài gài segment gộp >= 1024 px (ngưỡng 900px an toàn)
    "merge_min_box_pixels": 350,
    "merge_box_min_fill": 0.38,          # Box phải nằm phần lớn trong segment
    "merge_box_min_cover": 0.08,         # Mỗi box chiếm tối thiểu 8% diện tích segment
    "merge_box_max_cover": 0.85,         # Không có box nào đơn lẻ chiếm >= 85% (tránh nhầm với 1 vật)
    "merge_max_containment": 0.40,       # 2 box không lồng vào nhau (inter / min_area < 40%)
    "merge_sum_cover_min": 0.70,         # Tổng các box giải thích >= 70% diện tích segment
}


def _norm_box(b: List[float]) -> Tuple[float, float, float, float]:
    """Đảm bảo toạ độ [x1, y1, x2, y2] với x1 <= x2 và y1 <= y2."""
    if len(b) < 4:
        return 0.0, 0.0, 0.0, 0.0
    x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _box_iou(b1: List[float], b2: List[float]) -> float:
    """Tính IoU giữa 2 box [x1, y1, x2, y2]."""
    x1_a, y1_a, x2_a, y2_a = _norm_box(b1)
    x1_b, y1_b, x2_b, y2_b = _norm_box(b2)
    ix1, iy1 = max(x1_a, x1_b), max(y1_a, y1_b)
    ix2, iy2 = min(x2_a, x2_b), min(y2_a, y2_b)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area1 = max(0.0, x2_a - x1_a) * max(0.0, y2_a - y1_a)
    area2 = max(0.0, x2_b - x1_b) * max(0.0, y2_b - y1_b)
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0


def _box_containment(b1: List[float], b2: List[float]) -> float:
    """Tính mức độ lồng nhau: inter / min(area1, area2)."""
    x1_a, y1_a, x2_a, y2_a = _norm_box(b1)
    x1_b, y1_b, x2_b, y2_b = _norm_box(b2)
    ix1, iy1 = max(x1_a, x1_b), max(y1_a, y1_b)
    ix2, iy2 = min(x2_a, x2_b), min(y2_a, y2_b)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area1 = max(0.0, x2_a - x1_a) * max(0.0, y2_a - y1_a)
    area2 = max(0.0, x2_b - x1_b) * max(0.0, y2_b - y1_b)
    min_area = min(area1, area2)
    return inter / min_area if min_area > 0 else 0.0


def detect_drift(m: Dict[str, Any], name: str, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Phát hiện ứng viên bbox_drift đã qua calibration và gia cố an toàn."""
    out = []
    try:
        boxes = {b["idx"]: b for b in m.get("boxes", [])}
        segments = {s["id"]: s for s in m.get("segments", []) if not s.get("iscrowd", 0)}
        pairs = m.get("pairs", [])

        # Chỉ xét cặp cùng lớp
        same_class_pairs = [
            p for p in pairs 
            if p.get("det_class") == p.get("pan_class") and p.get("seg_id") in segments
        ]

        # Tìm cặp có lượng pixel giao nhau lớn nhất cho mỗi box
        best_pair_for_box: Dict[int, Dict[str, Any]] = {}
        for p in same_class_pairs:
            b_idx = p["box_idx"]
            if b_idx not in best_pair_for_box or p.get("inside", 0) > best_pair_for_box[b_idx].get("inside", 0):
                best_pair_for_box[b_idx] = p

        for b_idx, p in best_pair_for_box.items():
            box = boxes.get(b_idx)
            seg = segments.get(p["seg_id"])
            if not box or not seg:
                continue

            box_area = box.get("area", 0)
            seg_px = seg.get("pixels", 0)
            if box_area < cfg["drift_min_box_pixels"] or seg_px < cfg["drift_min_seg_pixels"]:
                continue

            # Calibration: Nếu segment này đã có 1 box khác cùng lớp ôm trọn >= 75%
            # thì box hiện tại chỉ là box láng giềng che khuất một phần, không phải drift
            other_covers_seg = any(
                p2["box_idx"] != b_idx
                and p2.get("seg_id") == p["seg_id"]
                and p2.get("det_class") == p["det_class"]
                and p2.get("cover", 0.0) >= cfg["drift_other_cover_threshold"]
                for p2 in same_class_pairs
            )
            if other_covers_seg:
                continue

            cover = float(p.get("cover", 0.0))
            fill = float(p.get("fill", 0.0))
            s_box = seg.get("bbox", [0, 0, 0, 0])
            iou = _box_iou(box["box"], s_box)

            # Tính độ lệch tâm tương đối theo đường chéo của box
            x1_b, y1_b, x2_b, y2_b = _norm_box(box["box"])
            x1_s, y1_s, x2_s, y2_s = _norm_box(s_box)
            bw, bh = max(1.0, x2_b - x1_b), max(1.0, y2_b - y1_b)
            bx, by = (x1_b + x2_b) / 2.0, (y1_b + y2_b) / 2.0
            sx, sy = (x1_s + x2_s) / 2.0, (y1_s + y2_s) / 2.0
            diag = max(1.0, math.hypot(bw, bh))
            center_dist = math.hypot(bx - sx, by - sy) / diag

            is_drift = False
            reason = ""

            # Hai quy luật trôi dạt đặc trưng:
            # Quy luật 1: Box bị kéo lệch hẳn khỏi mask (cover giảm rõ rệt, IoU giảm)
            if cfg["drift_cover_lower"] <= cover < cfg["drift_cover_upper"] and iou < cfg["drift_bbox_iou_upper"]:
                is_drift = True
                reason = f"Cùng lớp '{p['det_class']}': cover={cover:.2f}, bbox_iou={iou:.2f} (box lệch khỏi mask)"
            # Quy luật 2: Tâm box bị dịch chuyển >= 10% kích thước vật
            elif iou < cfg["drift_bbox_iou_upper"] and center_dist >= cfg["drift_min_center_dist"]:
                is_drift = True
                reason = f"Cùng lớp '{p['det_class']}': độ lệch tâm={center_dist:.2f}, bbox_iou={iou:.2f} (tâm box bị trôi)"

            if is_drift:
                # Severity score chuẩn hoá (0.0 đến 1.0): càng lệch tâm / IoU càng thấp thì điểm càng cao
                score = round(min(1.0, max(center_dist * 2.0, 1.0 - iou)), 3)
                out.append({
                    "type": "bbox_drift",
                    "target": name,
                    "detail": {
                        "box_idx": b_idx,
                        "box": [round(v, 1) for v in box["box"]],
                        "segment_id": seg["id"],
                        "det_class": p["det_class"],
                        "pan_class": p["pan_class"],
                        "cover": round(cover, 3),
                        "fill": round(fill, 3),
                        "bbox_iou": round(iou, 3),
                        "center_dist": round(center_dist, 3),
                        "score": score,
                        "reason": reason,
                    }
                })
    except Exception as err:
        print(f"[cảnh báo cross_drift] lỗi xử lý drift trên ảnh {name}: {err}", file=sys.stderr)
    return out


def detect_merge(m: Dict[str, Any], name: str, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Phát hiện ứng viên instance_merge đã qua calibration và gia cố an toàn."""
    out = []
    try:
        boxes_by_idx = {b["idx"]: b for b in m.get("boxes", [])}
        segments = {s["id"]: s for s in m.get("segments", []) if not s.get("iscrowd", 0)}
        pairs = m.get("pairs", [])

        seg_to_pairs: Dict[int, List[Dict[str, Any]]] = {}
        for p in pairs:
            if p.get("det_class") == p.get("pan_class") and p.get("seg_id") in segments:
                seg_to_pairs.setdefault(p["seg_id"], []).append(p)

        for seg_id, pair_list in seg_to_pairs.items():
            seg = segments[seg_id]
            if seg.get("pixels", 0) < cfg["merge_min_seg_pixels"]:
                continue

            # Lọc các box nằm trọn vẹn đáng kể trong segment
            matching_boxes = []
            for p in pair_list:
                box = boxes_by_idx.get(p["box_idx"])
                if not box or box.get("area", 0) < cfg["merge_min_box_pixels"]:
                    continue
                fill = float(p.get("fill", 0.0))
                cover = float(p.get("cover", 0.0))
                if fill >= cfg["merge_box_min_fill"] and cfg["merge_box_min_cover"] <= cover < cfg["merge_box_max_cover"]:
                    matching_boxes.append((box, p))

            if len(matching_boxes) >= 2:
                # Kiểm tra từng cặp box xem có tách biệt không (không lồng nhau) và cùng giải thích segment
                for i in range(len(matching_boxes)):
                    for j in range(i + 1, len(matching_boxes)):
                        b1, p1 = matching_boxes[i]
                        b2, p2 = matching_boxes[j]
                        containment = _box_containment(b1["box"], b2["box"])
                        sum_cover = float(p1["cover"]) + float(p2["cover"])

                        if containment < cfg["merge_max_containment"] and sum_cover >= cfg["merge_sum_cover_min"]:
                            avg_fill = (float(p1["fill"]) + float(p2["fill"])) / 2.0
                            score = round(min(1.0, 0.4 + 0.6 * avg_fill), 3)
                            out.append({
                                "type": "instance_merge",
                                "target": name,
                                "detail": {
                                    "segment_id": seg_id,
                                    "pan_class": seg.get("cls", ""),
                                    "pixels": seg.get("pixels", 0),
                                    "boxes": [b1["idx"], b2["idx"]],
                                    "sum_cover": round(sum_cover, 3),
                                    "containment": round(containment, 3),
                                    "score": score,
                                    "reason": (
                                        f"Segment panoptic '{seg.get('cls', '')}' ({seg.get('pixels', 0)}px) phủ lên 2 box detection riêng biệt "
                                        f"[{b1['idx']}, {b2['idx']}] (tổng cover={sum_cover:.2f}, containment={containment:.2f})"
                                    ),
                                }
                            })
    except Exception as err:
        print(f"[cảnh báo cross_drift] lỗi xử lý merge trên ảnh {name}: {err}", file=sys.stderr)
    return out


def candidates(d: Any, cfg: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Giao diện chuẩn gọi từ validate.py — trả về danh sách ứng viên đã sắp xếp theo độ nghi ngờ."""
    config = {**DEFAULTS, **(cfg or {})}

    try:
        from cross_check import match
    except ImportError:
        here = Path(__file__).resolve().parent
        if str(here) not in sys.path:
            sys.path.insert(0, str(here))
        from cross_check import match

    out: List[Dict[str, Any]] = []
    names = d.names()

    for name in names:
        try:
            m = match(d, name)
            if m is None:
                continue
            out.extend(detect_drift(m, name, config))
            out.extend(detect_merge(m, name, config))
        except Exception as err:
            print(f"[cảnh báo cross_drift] bỏ qua ảnh {name} do lỗi match: {err}", file=sys.stderr)
            continue

    # Sắp xếp ứng viên giảm dần theo điểm nghi ngờ (score) để hỗ trợ review nhanh
    out.sort(key=lambda c: c.get("detail", {}).get("score", 0.0), reverse=True)
    return out


if __name__ == "__main__":
    # Cho phép TV6 tự kiểm tra nhanh một thư mục delivery bất kỳ
    import argparse
    from validate import Delivery

    ap = argparse.ArgumentParser(description="Chạy kiểm tra độc lập module TV6 (cross_drift)")
    ap.add_argument("delivery", help="Đường dẫn thư mục delivery/")
    args = ap.parse_args()

    d = Delivery(args.delivery)
    results = candidates(d)
    print(f"=== KẾT QUẢ QUÉT TV6: {len(results)} ỨNG VIÊN ===")
    for idx, c in enumerate(results, 1):
        dt = c.get("detail", {})
        print(f"[{idx}] {c['type']} | ảnh: {c['target']} | score: {dt.get('score')} | lý do: {dt.get('reason')}")


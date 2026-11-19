"""TV6 — Đối chiếu phần 2: bbox_drift và instance_merge; đo nhiễu trên lô sạch.

Module đã được CALIBRATE (chuẩn hóa ngưỡng & loại bỏ nhiễu tự nhiên dựa trên
nguyên lý Mutual Best Match và Non-containment).

Giao diện theo khung validator (validate.py):
    candidates(d) -> list[dict]
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Cấu hình các ngưỡng đã qua Calibrate
DEFAULTS = {
    # --- bbox_drift ---
    "drift_min_box_pixels": 800,        # Bỏ qua box quá nhỏ để tránh nhiễu tự nhiên
    "drift_min_seg_pixels": 600,        # Bỏ qua mask quá nhỏ
    "drift_cover_upper": 0.70,          # Cover < 0.70 khi bị trôi
    "drift_cover_lower": 0.15,
    "drift_bbox_iou_upper": 0.65,       # IoU giữa detection box và segment bbox
    "drift_min_center_dist": 0.10,      # Độ lệch tâm tương đối (>= 10% đường chéo box)
    "drift_other_cover_threshold": 0.75,# Nếu segment đã có box khác ôm trọn >= 75% thì bỏ qua
    
    # --- instance_merge ---
    "merge_min_seg_pixels": 900,        # Đề bài gài segment gộp >= 1024 px
    "merge_min_box_pixels": 350,
    "merge_box_min_fill": 0.38,         # Box phải nằm phần lớn trong segment
    "merge_box_min_cover": 0.08,        # Mỗi box chiếm tối thiểu 8% diện tích segment
    "merge_box_max_cover": 0.85,        # Không có box nào đơn lẻ chiếm >= 85% (vì nếu có thì không phải 2 vật gộp)
    "merge_max_containment": 0.40,      # 2 box không lồng vào nhau (inter / min(area1, area2) < 40%)
    "merge_sum_cover_min": 0.70,        # Tổng các box giải thích >= 70% diện tích segment
}


def _box_iou(b1: List[int], b2: List[int]) -> float:
    """Tính IoU giữa 2 box [x1, y1, x2, y2]."""
    ix1, iy1 = max(b1[0], b2[0]), max(b1[1], b2[1])
    ix2, iy2 = min(b1[2], b2[2]), min(b1[3], b2[3])
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area1 = max(0, b1[2] - b1[0]) * max(0, b1[3] - b1[1])
    area2 = max(0, b2[2] - b2[0]) * max(0, b2[3] - b2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0


def _box_containment(b1: List[int], b2: List[int]) -> float:
    """Tính mức độ lồng nhau inter / min(area1, area2)."""
    ix1, iy1 = max(b1[0], b2[0]), max(b1[1], b2[1])
    ix2, iy2 = min(b1[2], b2[2]), min(b1[3], b2[3])
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area1 = max(0, b1[2] - b1[0]) * max(0, b1[3] - b1[1])
    area2 = max(0, b2[2] - b2[0]) * max(0, b2[3] - b2[1])
    min_area = min(area1, area2)
    return inter / min_area if min_area > 0 else 0.0


def _seg_bbox_to_xyxy(s_bbox: List[float]) -> List[int]:
    """Chuyển COCO segment bbox [x, y, w, h] sang [x1, y1, x2, y2]."""
    if len(s_bbox) < 4:
        return [0, 0, 0, 0]
    x, y, w, h = s_bbox[:4]
    return [int(round(x)), int(round(y)), int(round(x + w)), int(round(y + h))]


def detect_drift(m: Dict[str, Any], name: str, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Phát hiện ứng viên bbox_drift sau calibration."""
    out = []
    boxes = m.get("boxes", [])
    segments = {s["id"]: s for s in m.get("segments", []) if not s.get("iscrowd", 0)}
    pairs = m.get("pairs", [])

    # Chỉ xét cặp cùng lớp
    same_class_pairs = [
        p for p in pairs 
        if p["det_class"] == p["pan_class"] and p["seg_id"] in segments
    ]

    # Tìm cặp có lượng giao lớn nhất cho mỗi box
    best_pair_for_box: Dict[int, Dict[str, Any]] = {}
    for p in same_class_pairs:
        b_idx = p["box_idx"]
        if b_idx not in best_pair_for_box or p["inside"] > best_pair_for_box[b_idx]["inside"]:
            best_pair_for_box[b_idx] = p

    for b_idx, p in best_pair_for_box.items():
        box = next((b for b in boxes if b["idx"] == b_idx), None)
        seg = segments.get(p["seg_id"])
        if not box or not seg:
            continue

        box_area = box["area"]
        seg_px = seg["pixels"]
        if box_area < cfg["drift_min_box_pixels"] or seg_px < cfg["drift_min_seg_pixels"]:
            continue

        # Calibration: Kiểm tra xem segment này đã có 1 box khác cùng lớp ôm trọn chưa
        # Nếu có box khác cover >= 75% thì box hiện tại chỉ là box láng giềng/che khuất
        other_covers_seg = any(
            p2["box_idx"] != b_idx
            and p2["seg_id"] == p["seg_id"]
            and p2["det_class"] == p["det_class"]
            and p2["cover"] >= cfg["drift_other_cover_threshold"]
            for p2 in same_class_pairs
        )
        if other_covers_seg:
            continue

        cover = p["cover"]
        fill = p["fill"]
        s_box = _seg_bbox_to_xyxy(seg.get("bbox", []))
        iou = _box_iou(box["box"], s_box)

        # Tính độ lệch tâm tương đối
        bw, bh = box["box"][2] - box["box"][0], box["box"][3] - box["box"][1]
        bx, by = (box["box"][0] + box["box"][2]) / 2, (box["box"][1] + box["box"][3]) / 2
        sx, sy = (s_box[0] + s_box[2]) / 2, (s_box[1] + s_box[3]) / 2
        diag = max(1.0, math.hypot(bw, bh))
        center_dist = math.hypot(bx - sx, by - sy) / diag

        is_drift = False
        reason = ""
        
        # Dấu hiệu drift đã calibrate:
        if cfg["drift_cover_lower"] <= cover < cfg["drift_cover_upper"] and iou < cfg["drift_bbox_iou_upper"]:
            is_drift = True
            reason = f"Cùng lớp '{p['det_class']}': cover={cover:.2f}, bbox_iou={iou:.2f} (box lệch khỏi mask)"
        elif iou < cfg["drift_bbox_iou_upper"] and center_dist >= cfg["drift_min_center_dist"]:
            is_drift = True
            reason = f"Cùng lớp '{p['det_class']}': độ lệch tâm={center_dist:.2f}, bbox_iou={iou:.2f} (tâm box bị trôi)"

        if is_drift:
            score = round(max(center_dist, 1.0 - iou), 3)
            out.append({
                "type": "bbox_drift",
                "target": name,
                "detail": {
                    "box_idx": b_idx,
                    "box": box["box"],
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
    return out


def detect_merge(m: Dict[str, Any], name: str, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Phát hiện ứng viên instance_merge sau calibration."""
    out = []
    boxes_by_idx = {b["idx"]: b for b in m.get("boxes", [])}
    segments = {s["id"]: s for s in m.get("segments", []) if not s.get("iscrowd", 0)}
    pairs = m.get("pairs", [])

    seg_to_pairs: Dict[int, List[Dict[str, Any]]] = {}
    for p in pairs:
        if p["det_class"] == p["pan_class"] and p["seg_id"] in segments:
            seg_to_pairs.setdefault(p["seg_id"], []).append(p)

    for seg_id, pair_list in seg_to_pairs.items():
        seg = segments[seg_id]
        if seg["pixels"] < cfg["merge_min_seg_pixels"]:
            continue

        # Lọc các box nằm trọn vẹn đáng kể trong segment
        matching_boxes = []
        for p in pair_list:
            box = boxes_by_idx.get(p["box_idx"])
            if not box or box["area"] < cfg["merge_min_box_pixels"]:
                continue
            # Calibration: Box không được đơn lẻ chiếm trọn mask (vì nếu cover >= 85% thì là 1 vật hoàn chỉnh)
            if p["fill"] >= cfg["merge_box_min_fill"] and cfg["merge_box_min_cover"] <= p["cover"] < cfg["merge_box_max_cover"]:
                matching_boxes.append((box, p))

        if len(matching_boxes) >= 2:
            # Calibration: Kiểm tra 2 box không được lồng vào nhau (không phải box cha - box con)
            # và tổng độ phủ của chúng phải giải thích được phần lớn mask (sum cover >= 70%)
            for i in range(len(matching_boxes)):
                for j in range(i + 1, len(matching_boxes)):
                    b1, p1 = matching_boxes[i]
                    b2, p2 = matching_boxes[j]
                    containment = _box_containment(b1["box"], b2["box"])
                    sum_cover = p1["cover"] + p2["cover"]
                    
                    if containment < cfg["merge_max_containment"] and sum_cover >= cfg["merge_sum_cover_min"]:
                        avg_fill = (p1["fill"] + p2["fill"]) / 2.0
                        score = round(avg_fill, 3)
                        out.append({
                            "type": "instance_merge",
                            "target": name,
                            "detail": {
                                "segment_id": seg_id,
                                "pan_class": seg["cls"],
                                "pixels": seg["pixels"],
                                "boxes": [b1["idx"], b2["idx"]],
                                "sum_cover": round(sum_cover, 3),
                                "containment": round(containment, 3),
                                "score": score,
                                "reason": (
                                    f"Segment panoptic '{seg['cls']}' ({seg['pixels']}px) phủ lên 2 box detection riêng biệt "
                                    f"[{b1['idx']}, {b2['idx']}] (tổng cover={sum_cover:.2f}, containment={containment:.2f})"
                                ),
                            }
                        })
    return out


def candidates(d: Any, cfg: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Hàm chuẩn gọi từ validate.py."""
    config = {**DEFAULTS, **(cfg or {})}
    
    try:
        from cross_check import match
    except ImportError:
        import sys
        here = Path(__file__).resolve().parent
        if str(here) not in sys.path:
            sys.path.insert(0, str(here))
        from cross_check import match

    out: List[Dict[str, Any]] = []
    names = d.names()
    
    for name in names:
        m = match(d, name)
        out.extend(detect_drift(m, name, config))
        out.extend(detect_merge(m, name, config))
        
    return out

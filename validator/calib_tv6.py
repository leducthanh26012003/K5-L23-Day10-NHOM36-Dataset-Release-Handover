"""TV6 — Công cụ Calibration và đo nhiễu tự nhiên trên toàn bộ thông số (Bản siêu nhanh).

Nạp mask đúng 1 lần vào bộ nhớ, sau đó quét lưới tức thì trong vài giây.
    python validator/calib_tv6.py
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from validate import Delivery
import cross_check
import cross_drift


def main() -> int:
    t0 = time.time()
    print("=== TV6: BẮT ĐẦU CALIBRATION TOÀN BỘ THÔNG SỐ ===")

    runs_dir = ROOT / "runs"
    dataset_paths = {
        "clean": runs_dir / "clean" / "delivery",
        "r36": runs_dir / "r36" / "delivery",
        "r101": runs_dir / "r101" / "delivery",
        "r202": runs_dir / "r202" / "delivery",
    }

    deliveries = {}
    cached_matches: Dict[str, List[Tuple[str, Any]]] = {}

    for k, p in dataset_paths.items():
        if p.exists():
            d = Delivery(p)
            deliveries[k] = d
            print(f"- Nạp và trích xuất đặc trưng {k:<6} ({len(d.names())} ảnh)...", end="", flush=True)
            t_d0 = time.time()
            matches = []
            for name in d.names():
                m = cross_check.match(d, name)
                if m:
                    matches.append((name, m))
            cached_matches[k] = matches
            print(f" xong trong {time.time() - t_d0:.1f}s")

    clean_matches = cached_matches.get("clean", [])
    if not clean_matches:
        print("[LỖI] Thiếu dữ liệu lô sạch runs/clean/delivery.", file=sys.stderr)
        return 1

    # 1. Phân tích phân phối thực tế trên cùng lớp (Same-class Pairs) trên lô sạch
    print("\n--- 1. PHÂN PHỐI LỆCH TỰ NHIÊN TRÊN LÔ SẠCH (50 ảnh COCO) ---")
    all_cdist, all_iou, all_cover = [], [], []

    for name, m in clean_matches:
        boxes = {b["idx"]: b for b in m.get("boxes", [])}
        segments = {s["id"]: s for s in m.get("segments", []) if not s.get("iscrowd", 0)}

        for p in m.get("pairs", []):
            if p.get("det_class") == p.get("pan_class") and p.get("seg_id") in segments:
                b = boxes.get(p["box_idx"])
                s = segments.get(p["seg_id"])
                if not b or not s:
                    continue
                if b["area"] < 800 or s["pixels"] < 600:
                    continue

                x1_b, y1_b, x2_b, y2_b = cross_drift._norm_box(b["box"])
                x1_s, y1_s, x2_s, y2_s = cross_drift._norm_box(s["bbox"])
                bw, bh = max(1.0, x2_b - x1_b), max(1.0, y2_b - y1_b)
                bx, by = (x1_b + x2_b) / 2.0, (y1_b + y2_b) / 2.0
                sx, sy = (x1_s + x2_s) / 2.0, (y1_s + y2_s) / 2.0
                diag = max(1.0, math.hypot(bw, bh))
                cdist = math.hypot(bx - sx, by - sy) / diag
                iou = cross_drift._box_iou(b["box"], s["bbox"])
                cover = p.get("cover", 0.0)

                all_cdist.append(cdist)
                all_iou.append(iou)
                all_cover.append(cover)

    all_cdist.sort()
    all_iou.sort()
    all_cover.sort()
    n = len(all_cdist)
    print(f"Tổng số cặp cùng lớp (box>=800px, seg>=600px): {n} cặp")
    if n > 0:
        print(f"- Center dist: min={all_cdist[0]:.4f}, 50%={all_cdist[n//2]:.4f}, 90%={all_cdist[int(n*0.9)]:.4f}, max={all_cdist[-1]:.4f}")
        print(f"- BBox IoU   : min={all_iou[0]:.4f}, 10%={all_iou[int(n*0.1)]:.4f}, 50%={all_iou[n//2]:.4f}, max={all_iou[-1]:.4f}")
        print(f"- Mask Cover : min={all_cover[0]:.4f}, 10%={all_cover[int(n*0.1)]:.4f}, 50%={all_cover[n//2]:.4f}, max={all_cover[-1]:.4f}")

    # 2. Quét lưới thông số chọn ngưỡng tối ưu cho bbox_drift
    print("\n--- 2. KẾT QUẢ QUÉT LƯỚI THÔNG SỐ (GRID SEARCH BBOX_DRIFT) ---")
    d_cdists = [0.08, 0.10, 0.12, 0.15]
    d_ious = [0.70, 0.75, 0.78, 0.82]
    d_covers = [0.65, 0.70, 0.75]

    print(f"{'cdist':<7} | {'iou_up':<7} | {'cov_up':<7} | {'clean':<6} | {'r36':<6} | {'r101':<6} | {'r202':<6} | {'Ghi chú'}")
    print("-" * 75)

    base_cfg = dict(cross_drift.DEFAULTS)

    for cdist in d_cdists:
        for iou_up in d_ious:
            for cov_up in d_covers:
                cfg = dict(base_cfg)
                cfg["drift_min_center_dist"] = cdist
                cfg["drift_bbox_iou_upper"] = iou_up
                cfg["drift_cover_upper"] = cov_up

                row = {}
                for k, mlist in cached_matches.items():
                    n_drift = 0
                    for name, m in mlist:
                        n_drift += len(cross_drift.detect_drift(m, name, cfg))
                    row[k] = n_drift

                clean_tot = row.get("clean", 0)
                r36_tot = row.get("r36", 0)
                r101_tot = row.get("r101", 0)
                r202_tot = row.get("r202", 0)

                note = ""
                if clean_tot == 0:
                    if iou_up == 0.78 and cdist == 0.10 and cov_up == 0.70:
                        note = "<-- TỐI ƯU ĐÃ CHỌN"
                    else:
                        note = "Hợp lệ (0 nhiễu)"
                else:
                    note = f"Có {clean_tot} báo giả!"

                print(f"{cdist:<7.2f} | {iou_up:<7.2f} | {cov_up:<7.2f} | {clean_tot:<6} | {r36_tot:<6} | {r101_tot:<6} | {r202_tot:<6} | {note}")

    # 3. Kiểm tra độ nhạy của instance_merge
    print("\n--- 3. CALIBRATION THÔNG SỐ INSTANCE_MERGE ---")
    for min_seg in [800, 900, 1000]:
        for min_fill in [0.30, 0.38, 0.45]:
            cfg_merge = dict(base_cfg)
            cfg_merge["merge_min_seg_pixels"] = min_seg
            cfg_merge["merge_box_min_fill"] = min_fill

            row_m = {}
            for k, mlist in cached_matches.items():
                n_m = 0
                for name, m in mlist:
                    n_m += len(cross_drift.detect_merge(m, name, cfg_merge))
                row_m[k] = n_m

            note = "<-- TỐI ƯU ĐÃ CHỌN" if (min_seg == 900 and min_fill == 0.38) else ""
            print(f"min_seg={min_seg:4d}px | min_fill={min_fill:.2f} -> clean: {row_m.get('clean', 0)} | r36: {row_m.get('r36', 0)} | r101: {row_m.get('r101', 0)} | r202: {row_m.get('r202', 0)} {note}")

    # 4. Kiểm tra thông số của TV3 (cross_check)
    print("\n--- 4. KIỂM CHỨNG THÔNG SỐ TV3 (CROSS_CHECK) TRÊN CÁC LÔ ---")
    for k, d in deliveries.items():
        c_tv3 = cross_check.candidates(d)
        counts = {}
        for c in c_tv3:
            counts[c["type"]] = counts.get(c["type"], 0) + 1
        print(f"Lô {k:<6}: {len(c_tv3)} ứng viên TV3 {counts}")

    print(f"\nThời gian calibration: {time.time() - t0:.1f}s")
    print("=== HOÀN TẤT CALIBRATION ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

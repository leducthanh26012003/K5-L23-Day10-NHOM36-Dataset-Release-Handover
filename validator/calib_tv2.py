"""Đo nhiễu tự nhiên để chọn ngưỡng cho 5 luật của TV2 (chạy trên lô sạch).

  py validator/calib_tv2.py runs/clean/delivery

In ra:
  1. Độ tràn mép lớn nhất của box (để chọn EPS cho bbox_out_of_bounds).
  2. Các cặp box cùng lớp gần giống nhau nhất (để chứng minh ngưỡng duplicate_box không bắt nhầm).
  3. Chênh lệch area khai báo - số pixel thật (để chọn dung sai cho thing_overlap).
  4. Số class_id / category_id không hợp lệ (lô sạch phải là 0).
Chỉ đọc thư mục delivery được truyền vào.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_delivery, pixel_counts, read_labels  # noqa: E402


def main() -> int:
    t0 = time.time()
    ctx = load_delivery(sys.argv[1])
    names = sorted(ctx["manifest"])

    # 1. Tràn mép
    worst = (0.0, None)
    n_boxes = 0
    for name in names:
        for c, x, y, w, h in read_labels(ctx, name):
            n_boxes += 1
            over = max(-(x - w / 2), -(y - h / 2), x + w / 2 - 1, y + h / 2 - 1)
            if over > worst[0]:
                worst = (over, name)
    print(f"[1] {n_boxes} box; tràn mép lớn nhất = {worst[0]:.6f} (ảnh {worst[1]})")

    # 2. Cặp box cùng lớp gần giống nhau: sắp theo (chênh kích thước, lệch tâm), tính bằng pixel
    pairs = []
    for name in names:
        W, H = ctx["size"][name]
        rows = read_labels(ctx, name)
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                if int(a[0]) != int(b[0]):
                    continue
                dsize = max(abs(a[3] - b[3]) * W, abs(a[4] - b[4]) * H)
                dcenter = max(abs(a[1] - b[1]) * W, abs(a[2] - b[2]) * H)
                pairs.append((dsize + dcenter, dsize, dcenter, name, ctx["classes"].get(int(a[0]))))
    pairs.sort()
    print(f"[2] {len(pairs)} cặp box cùng lớp; 5 cặp giống nhau nhất (chênh kích thước px, lệch tâm px):")
    for _, ds, dc, name, cls in pairs[:5]:
        print(f"     {name} {cls:<14} kích thước {ds:7.2f}  tâm {dc:7.2f}")

    # 3. area khai báo so với pixel thật
    diffs = []
    for name in names:
        counts = pixel_counts(ctx, name)
        for s in ctx["segments"].get(name, []):
            diffs.append((s["area"] - counts.get(s["id"], 0), name, s["id"]))
    pos = [d for d in diffs if d[0] > 0]
    neg = [d for d in diffs if d[0] < 0]
    print(f"[3] {len(diffs)} segment; area > pixel thật: {len(pos)}; area < pixel thật: {len(neg)}; "
          f"lệch dương lớn nhất = {max((d[0] for d in diffs), default=0)}")

    # 4. id không hợp lệ
    bad_cls = sum(1 for n in names for r in read_labels(ctx, n) if not (0 <= r[0] < 80 and r[0] == int(r[0])))
    bad_cat = sum(1 for segs in ctx["segments"].values() for s in segs if s["category_id"] not in ctx["categories"])
    print(f"[4] class_id không hợp lệ: {bad_cls}; category_id không hợp lệ: {bad_cat}")
    print(f"Thời gian: {time.time() - t0:.1f}s cho {len(names)} ảnh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

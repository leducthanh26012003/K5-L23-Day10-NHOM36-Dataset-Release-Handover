"""5 luật nhãn của TV2: invalid_class, bbox_out_of_bounds, duplicate_box, invalid_category_id, thing_overlap.

Mỗi hàm check_* nhận ctx (common.load_delivery) và trả list {"type", "target"}, target là tên ảnh.
Hàm KHÔNG lọc "mỗi ảnh một lỗi": validate.py (TV1) làm việc đó theo thứ tự ưu tiên.

Ngưỡng chọn bằng số đo trên lô sạch (py validator/calib_tv2.py runs/clean/delivery):
  - tràn mép tự nhiên lớn nhất 0.000001 (làm tròn số)            -> OOB_EPS = 1e-4
  - cặp box cùng lớp tự nhiên giống nhau nhất: chênh kích thước 2.1 px, lệch tâm 3.2 px
    box bị chép: chênh kích thước 0 px, lệch tâm 1-2 px             -> DUP_SIZE_PX = 1, DUP_CENTER_PX = 3
  - area khai báo == số pixel thật ở 643/643 segment               -> OVERLAP_TOL = 0

Chạy thử riêng phần này:
  py validator/rules_label.py runs/clean/delivery        # lô sạch phải in 0 lỗi
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_delivery, pixel_counts, read_labels  # noqa: E402

N_CLASSES = 80        # class_id hợp lệ: 0..79
OOB_EPS = 1e-4        # sai số cho phép khi so cạnh box với mép ảnh (toạ độ chuẩn hoá)
DUP_SIZE_PX = 1.0     # hai box "cùng kích thước" nếu w và h lệch nhau không quá 1 pixel
DUP_CENTER_PX = 3.0   # và tâm lệch nhau không quá 3 pixel theo mỗi trục
OVERLAP_TOL = 0       # area khai báo được phép lớn hơn số pixel thật bao nhiêu


def _err(kind: str, name: str) -> dict:
    return {"type": kind, "target": name}


def check_invalid_class(ctx: dict) -> list[dict]:
    """class_id phải là số nguyên trong 0..79."""
    out = []
    for name in sorted(ctx["manifest"]):
        for c, *_ in read_labels(ctx, name):
            if c != int(c) or not 0 <= int(c) < N_CLASSES:
                out.append(_err("invalid_class", name))
                break
    return out


def check_bbox_out_of_bounds(ctx: dict) -> list[dict]:
    """Một trong 4 cạnh của box vượt ra ngoài [0, 1] (có thể chỉ tràn một chút)."""
    out = []
    for name in sorted(ctx["manifest"]):
        for _, x, y, w, h in read_labels(ctx, name):
            left, top, right, bottom = x - w / 2, y - h / 2, x + w / 2, y + h / 2
            if left < -OOB_EPS or top < -OOB_EPS or right > 1 + OOB_EPS or bottom > 1 + OOB_EPS:
                out.append(_err("bbox_out_of_bounds", name))
                break
    return out


def _is_duplicate(a, b, width: int, height: int) -> bool:
    """Cùng lớp, cùng kích thước, tâm chỉ lệch vài pixel. Không dùng IoU:
    COCO có cặp box thật chồng nhau tới IoU ~0.66 nhưng khác kích thước."""
    if int(a[0]) != int(b[0]):
        return False
    same_size = abs(a[3] - b[3]) * width <= DUP_SIZE_PX and abs(a[4] - b[4]) * height <= DUP_SIZE_PX
    near = abs(a[1] - b[1]) * width <= DUP_CENTER_PX and abs(a[2] - b[2]) * height <= DUP_CENTER_PX
    return same_size and near


def check_duplicate_box(ctx: dict) -> list[dict]:
    out = []
    for name in sorted(ctx["manifest"]):
        if name not in ctx["size"]:
            continue
        width, height = ctx["size"][name]
        rows = read_labels(ctx, name)
        if any(_is_duplicate(rows[i], rows[j], width, height)
               for i in range(len(rows)) for j in range(i + 1, len(rows))):
            out.append(_err("duplicate_box", name))
    return out


def check_invalid_category_id(ctx: dict) -> list[dict]:
    """category_id phải có trong danh sách categories (id COCO có khoảng trống, không kiểm theo khoảng số)."""
    valid = set(ctx["categories"])
    return [_err("invalid_category_id", name) for name, segs in sorted(ctx["segments"].items())
            if name in ctx["manifest"] and any(s["category_id"] not in valid for s in segs)]


def check_thing_overlap(ctx: dict) -> list[dict]:
    """Vật bị vật khác đè trong mask (mất pixel) nhưng area vẫn khai số cũ: area > số pixel thật.
    So '>' chứ không '!=': vật đè lên đã được cập nhật area đúng, chỉ vật bị mất pixel mới lệch."""
    out = []
    for name, segs in sorted(ctx["segments"].items()):
        if name not in ctx["manifest"]:
            continue
        counts = pixel_counts(ctx, name)  # id 0 (nền) không có segment nào nên tự bị bỏ qua
        if any(s["area"] > counts.get(s["id"], 0) + OVERLAP_TOL for s in segs):
            out.append(_err("thing_overlap", name))
    return out


CHECKS = [check_invalid_class, check_bbox_out_of_bounds, check_duplicate_box,
          check_invalid_category_id, check_thing_overlap]


def run(ctx: dict) -> list[dict]:
    """Chạy cả 5 luật, trả mọi lỗi tìm được (một ảnh có thể xuất hiện ở nhiều luật)."""
    found = []
    for check in CHECKS:
        found += check(ctx)
    return found


def main() -> int:
    ctx = load_delivery(sys.argv[1])
    found = run(ctx)
    by_type: dict[str, list[str]] = {}
    for e in found:
        by_type.setdefault(e["type"], []).append(e["target"])
    for check in CHECKS:
        kind = check.__name__.removeprefix("check_")
        names = by_type.get(kind, [])
        print(f"{kind:<22} {len(names):>3}  {' '.join(names)}")
    print(f"Tổng: {len(found)} lỗi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

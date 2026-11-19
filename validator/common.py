"""Hàm đọc lô dùng chung cho cả nhóm (TV2 viết). Chỉ thư viện chuẩn.

Mọi module của validator nhận `ctx = load_delivery(<thư mục delivery>)`.
Chỉ đọc thư mục delivery được truyền vào: không đọc _private/, data_source/, không dùng mạng.

ctx gồm:
  dir         Path của thư mục delivery
  manifest    {tên ảnh: {"image", "label", "mask", "image_sha256", ...}}
  meta        {tên ảnh: {"scene_id", "split", "job_id", "guideline_version"}}
  jobs        {job_id: {"annotator", "reviewer", "guideline"}}
  classes     {0: "person", ..., 79: "toothbrush"}      (detection, classes.txt)
  categories  {id COCO: {"name", "isthing", ...}}       (panoptic.json)
  size        {tên ảnh: (width, height)}                (lấy từ panoptic.json, không mở JPG)
  segments    {tên ảnh: [segment_info, ...]}            (id, category_id, area, bbox, iscrowd)
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pngutil  # noqa: E402  (đọc PNG bằng thư viện chuẩn, được phép import)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_delivery(delivery) -> dict:
    """Đọc mọi file mô tả của lô một lần."""
    d = Path(delivery)
    pan = _json(d / "panoptic.json")
    with (d / "jobs.csv").open(encoding="utf-8", newline="") as f:
        jobs = {row["job_id"]: row for row in csv.DictReader(f)}
    classes = {}
    for line in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            idx, name = line.split(" ", 1)
            classes[int(idx)] = name.strip()
    return {
        "dir": d,
        "manifest": _json(d / "manifest.json")["items"],
        "meta": {m["image"]: m for m in _json(d / "metadata.json")["items"]},
        "jobs": jobs,
        "classes": classes,
        "categories": {c["id"]: c for c in pan["categories"]},
        # Khoá theo tên file bỏ đuôi: "000000000139.jpg" -> "000000000139" (đề ẩn: "img_0001")
        "size": {Path(im["file_name"]).stem: (im["width"], im["height"]) for im in pan["images"]},
        "segments": {Path(a["file_name"]).stem: a["segments_info"] for a in pan["annotations"]},
    }


def read_labels(ctx: dict, name: str) -> list[tuple[float, float, float, float, float]]:
    """Nhãn YOLO của một ảnh: list (cls, x, y, w, h) dạng số thực.

    Bỏ dòng trống và dòng thiếu cột; chịu được khoảng trắng thừa.
    cls để dạng float để luật invalid_class tự quyết (ví dụ "80" hay "2.5").
    """
    path = ctx["dir"] / ctx["manifest"][name]["label"]
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            rows.append(tuple(float(v) for v in parts[:5]))
        except ValueError:
            continue
    return rows


def yolo_to_px(row, width: int, height: int) -> tuple[int, float, float, float, float]:
    """(cls, x, y, w, h) chuẩn hoá -> (cls, x1, y1, x2, y2) theo pixel."""
    c, x, y, w, h = row
    return int(c), (x - w / 2) * width, (y - h / 2) * height, (x + w / 2) * width, (y + h / 2) * height


@lru_cache(maxsize=None)
def _read_mask(mask_path: str) -> tuple[int, int, bytes]:
    width, height, pixels = pngutil.read_rgb(Path(mask_path))
    return width, height, bytes(pixels)


def mask_path(ctx: dict, name: str) -> Path:
    return ctx["dir"] / ctx["manifest"][name]["mask"]


def pixel_counts(ctx: dict, name: str) -> dict[int, int]:
    """{segment_id: số pixel thật trong mask}. id = R + G*256 + B*65536; có cả id 0 (nền).

    Đếm bằng Counter trên bộ 3 byte (vòng lặp chạy trong C, nhanh hơn duyệt từng pixel).
    """
    path = mask_path(ctx, name)
    if not path.is_file():
        return {}
    _, _, p = _read_mask(str(path))
    counts = Counter(zip(p[0::3], p[1::3], p[2::3]))
    return {r + g * 256 + b * 65536: n for (r, g, b), n in counts.items()}


def segment_pixels(ctx: dict, name: str) -> tuple[int, int, dict[int, list[int]]]:
    """(width, height, {segment_id: [chỉ số pixel phẳng = y*width + x]}), bỏ id 0.

    Dùng cho phần đối chiếu (TV3, TV6): đếm pixel của segment nằm trong một box.
    Chậm hơn pixel_counts, chỉ gọi khi cần toạ độ.
    """
    path = mask_path(ctx, name)
    if not path.is_file():
        return 0, 0, {}
    width, height, p = _read_mask(str(path))
    out: dict[int, list[int]] = {}
    for idx, (r, g, b) in enumerate(zip(p[0::3], p[1::3], p[2::3])):
        sid = r + g * 256 + b * 65536
        if sid:
            out.setdefault(sid, []).append(idx)
    return width, height, out

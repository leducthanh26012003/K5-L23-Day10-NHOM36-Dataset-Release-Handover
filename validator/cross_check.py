"""TV3 — Đối chiếu detection <-> panoptic, phần 1.

- `match(d, name)`  : ghép box detection với segment thing của panoptic bằng PIXEL MASK (dùng chung với TV6).
- `candidates(d)`   : ứng viên `class_swap` / `category_swap` và `missing_box` cho người xem ảnh.

Chỉ đọc qua đối tượng `Delivery` (validate.py) và file trong thư mục delivery; chỉ thư viện chuẩn
(+ `scripts/pngutil.py` đọc PNG). Không dùng nhãn gốc, không ghi cứng tên ảnh.

Chạy riêng phần này (không cần các module khác):
    python validator/cross_check.py runs/r36/delivery --out runs/r36/cand_tv3.json [--pair-cover 0.7 ...]

Giao diện cho TV6 (`cross_drift.py`):
    from cross_check import match
    m = match(d, name)      # None nếu thiếu mask
    m["boxes"]    : [{"idx", "cls", "box": [x1, y1, x2, y2] (pixel, đã cắt vào ảnh), "area"}]
    m["segments"] : [{"id", "cls", "pixels" (đếm từ mask), "iscrowd", "bbox": [x1, y1, x2, y2]}]   # chỉ segment thing
    m["pairs"]    : [{"box_idx", "seg_id", "det_class", "pan_class",
                      "inside",  # số pixel của segment nằm trong box
                      "cover",   # inside / pixels của segment   (box ghép đúng -> gần 1)
                      "fill",    # inside / diện tích box
                      "iou"}]    # IoU bbox của box với bbox segment (segments_info), chỉ tham khảo
    m["width"], m["height"], m["image"]
"""
from __future__ import annotations

import sys
from array import array
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import pngutil  # noqa: E402  (thư viện chuẩn, đề cho phép import)

# Ngưỡng mặc định. TV6 chọn ngưỡng cuối cùng bằng cách đo trên lô sạch; truyền qua `candidates(d, th={...})`.
DEFAULTS = {
    "pair_cover": 0.70,      # cặp "trùng vị trí": >= 70% pixel của segment nằm trong box ...
    "pair_fill": 0.10,       # ... và segment chiếm >= 10% diện tích box (vật mảnh/xoè như chim, diều có fill ~0.2)
    "missing_area": 0.01,    # missing_box: segment thing >= 1% diện tích ảnh ...
    "missing_cover": 0.50,   # ... mà không box CÙNG LỚP nào chứa >= 50% pixel của nó
}


# ----------------------------------------------------------------------------- đọc dữ liệu
def _index(d) -> dict:
    """Chỉ mục panoptic theo tên ảnh (tạo một lần cho mỗi Delivery)."""
    idx = getattr(d, "_cross_index", None)
    if idx is not None:
        return idx
    pan = d.panoptic
    cats = {c["id"]: c for c in pan.get("categories", [])}
    images = {im["id"]: im for im in pan.get("images", [])}
    items = {}
    for ann in pan.get("annotations", []):
        im = images.get(ann.get("image_id"))
        if im is None:
            continue
        items[Path(im["file_name"]).stem] = {"width": im["width"], "height": im["height"],
                                             "mask": ann.get("file_name"), "segments": ann.get("segments_info", [])}
    idx = {"cats": cats, "items": items}
    d._cross_index = idx
    return idx


def _boxes(d, name: str, w: int, h: int) -> list[dict]:
    """Box YOLO -> pixel. Bỏ dòng hỏng và class không có trong classes.txt (luật của TV2 bắt lỗi đó)."""
    out = []
    for line_no, cols in d.label_rows(name) or []:
        if len(cols) != 5:
            continue
        try:
            cls = int(cols[0])
            xc, yc, bw, bh = (float(v) for v in cols[1:])
        except ValueError:
            continue
        if cls not in d.classes:
            continue
        x1, y1, x2, y2 = (xc - bw / 2) * w, (yc - bh / 2) * h, (xc + bw / 2) * w, (yc + bh / 2) * h
        out.append({"idx": line_no, "cls": d.classes[cls],
                    "box": [max(0.0, x1), max(0.0, y1), min(float(w), x2), min(float(h), y2)]})
    return out


def _segment_ids(path: Path) -> tuple[int, int, array]:
    """Mask PNG -> mảng id segment cho từng pixel (id = R + G*256 + B*256^2)."""
    w, h, rgb = pngutil.read_rgb(path)
    buf = bytearray(w * h * 4)                  # RGB + byte 0 = uint32 little-endian, nhanh hơn lặp từng pixel
    buf[0::4], buf[1::4], buf[2::4] = rgb[0::3], rgb[1::3], rgb[2::3]
    ids = array("I")
    ids.frombytes(bytes(buf))
    if sys.byteorder == "big":
        ids.byteswap()
    return w, h, ids


# ----------------------------------------------------------------------------- ghép
def _iou(a, b) -> float:
    """IoU hai bbox [x1, y1, x2, y2] (chỉ để tham khảo; tín hiệu chính là pixel mask)."""
    iw = min(a[2], b[2]) - max(a[0], b[0])
    ih = min(a[3], b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match(d, name: str) -> dict | None:
    idx = _index(d)
    it = idx["items"].get(name)
    if it is None:
        return None
    rel = d.manifest.get(name, {}).get("mask") or f"masks/{it['mask']}"
    path = d.path(rel)
    if not path.is_file():
        return None
    w, h, ids = _segment_ids(path)
    totals = Counter(ids)
    segments = []
    for s in it["segments"]:
        cat = idx["cats"].get(s.get("category_id"))
        if not cat or not cat.get("isthing"):
            continue                            # chỉ so vật đếm được (thing); category lạ là việc của TV2
        bx, by, bw, bh = s.get("bbox", [0, 0, 0, 0])
        segments.append({"id": s["id"], "cls": cat["name"], "pixels": totals.get(s["id"], 0),
                         "iscrowd": int(s.get("iscrowd", 0)), "bbox": [bx, by, bx + bw, by + bh]})
    seg_by_id = {s["id"]: s for s in segments}
    boxes, pairs = [], []
    for b in _boxes(d, name, w, h):
        x1, y1, x2, y2 = (int(round(v)) for v in b["box"])
        area = max(0, x2 - x1) * max(0, y2 - y1)
        boxes.append({"idx": b["idx"], "cls": b["cls"], "box": b["box"], "area": area})
        if area == 0:
            continue
        inside = Counter()
        for y in range(y1, y2):
            inside.update(ids[y * w + x1: y * w + x2])
        for sid, n in inside.items():
            s = seg_by_id.get(sid)
            if s is None or s["pixels"] == 0:
                continue
            pairs.append({"box_idx": b["idx"], "seg_id": sid, "det_class": b["cls"], "pan_class": s["cls"],
                          "inside": n, "cover": round(n / s["pixels"], 4), "fill": round(n / area, 4),
                          "iou": round(_iou(b["box"], s["bbox"]), 4)})
    return {"image": name, "width": w, "height": h, "boxes": boxes, "segments": segments, "pairs": pairs}


# ----------------------------------------------------------------------------- ứng viên
def _swaps(m: dict, th: dict) -> list[dict]:
    """Box và segment trùng vị trí (cặp tốt nhất của nhau) nhưng khác lớp; không bên nào có bạn cùng lớp."""
    segs = {s["id"]: s for s in m["segments"]}
    boxes = {b["idx"]: b for b in m["boxes"]}
    good = [p for p in m["pairs"]
            if p["cover"] >= th["pair_cover"] and p["fill"] >= th["pair_fill"] and not segs[p["seg_id"]]["iscrowd"]]
    best_box, best_seg = {}, {}
    for p in good:
        if p["inside"] > best_box.get(p["box_idx"], {"inside": -1})["inside"]:
            best_box[p["box_idx"]] = p
        if p["inside"] > best_seg.get(p["seg_id"], {"inside": -1})["inside"]:
            best_seg[p["seg_id"]] = p
    out = []
    for p in good:
        if p["det_class"] == p["pan_class"]:
            continue
        if best_box.get(p["box_idx"]) is not p or best_seg.get(p["seg_id"]) is not p:
            continue
        if any(q["box_idx"] == p["box_idx"] and q["pan_class"] == p["det_class"] for q in good):
            continue                            # box đã có segment cùng lớp
        if any(q["seg_id"] == p["seg_id"] and q["det_class"] == p["pan_class"] for q in good):
            continue                            # segment đã có box cùng lớp
        out.append({"type": "class_swap", "target": m["image"], "detail": {
            "need_review": "class_swap hoặc category_swap: mở ảnh xem nguồn nào ghi đúng vật",
            "box": [round(v, 1) for v in boxes[p["box_idx"]]["box"]], "label_line": p["box_idx"],
            "det_class": p["det_class"], "segment_id": p["seg_id"], "pan_class": p["pan_class"],
            "cover": p["cover"], "fill": p["fill"]}})
    return out


def _missing(m: dict, th: dict, skip: set) -> list[dict]:
    """Segment thing lớn (không crowd) mà không box cùng lớp nào chứa phần lớn pixel của nó."""
    img_area = m["width"] * m["height"]
    out = []
    for s in m["segments"]:
        if s["iscrowd"] or s["id"] in skip or s["pixels"] < th["missing_area"] * img_area:
            continue
        best = max((p["cover"] for p in m["pairs"] if p["seg_id"] == s["id"] and p["det_class"] == s["cls"]),
                   default=0.0)
        if best >= th["missing_cover"]:
            continue
        out.append({"type": "missing_box", "target": m["image"], "detail": {
            "segment_id": s["id"], "pan_class": s["cls"], "seg_bbox": [round(v, 1) for v in s["bbox"]],
            "seg_pixels": s["pixels"], "seg_share": round(s["pixels"] / img_area, 4), "best_same_class_cover": best}})
    return out


def candidates(d, th: dict | None = None) -> list[dict]:
    th = {**DEFAULTS, **(th or {})}
    out = []
    for name in d.names():
        m = match(d, name)
        if m is None:
            continue
        sw = _swaps(m, th)
        out += sw + _missing(m, th, {c["detail"]["segment_id"] for c in sw})
    return out


# ----------------------------------------------------------------------------- chạy riêng
def main(argv=None) -> int:
    import argparse
    import json
    from validate import Delivery

    ap = argparse.ArgumentParser(description="TV3: ứng viên class/category swap + missing_box")
    ap.add_argument("delivery")
    ap.add_argument("--out", required=True)
    for k, v in DEFAULTS.items():
        ap.add_argument("--" + k.replace("_", "-"), type=float, default=v)
    args = ap.parse_args(argv)
    th = {k: getattr(args, k) for k in DEFAULTS}
    cands = candidates(Delivery(args.delivery), th)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"thresholds": th, "candidates": cands}, ensure_ascii=False, indent=1) + "\n",
                              encoding="utf-8")
    kinds = Counter(c["type"] for c in cands)
    print(f"{len(cands)} ứng viên / {len({c['target'] for c in cands})} ảnh {dict(kinds)} -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())

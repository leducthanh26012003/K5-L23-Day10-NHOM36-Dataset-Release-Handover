#!/usr/bin/env python3
"""Vẽ box detection và viền segment panoptic lên ảnh để review bằng mắt (Pha 2, đề ẩn).

Công cụ CHỈ ĐỌC thư mục delivery. Ảnh vẽ ra ghi sang thư mục khác
(mặc định runs/view/<tên lô>, đã nằm trong .gitignore). Được dùng Pillow; validator thì không.

Xem vài ảnh:
  python tools/view.py runs/r36/delivery 000000000139 000000000285
  python tools/view.py runs/r36/delivery 000000000139 --box 3 --seg 3226956 --open

Xem cả hàng đợi ứng viên và chia việc cho nhóm:
  python tools/view.py runs/r36/delivery --candidates runs/r36/candidates.json --people TV1,TV2,TV3,TV4,TV5,TV6

candidates.json theo validator của nhóm:
  {"candidates": [{"type": "bbox_drift", "target": "<ảnh>", "detail": {"box_idx": 2, "segment_id": 5126, "reason": "..."}}]}
  Số box = SỐ DÒNG trong labels/<ảnh>.txt, ĐẾM TỪ 1 (như validate.py label_rows). Đọc từ
  detail.box_idx / detail.label_line / detail.boxes; segment từ detail.segment_id (= R + G*256 + B*256^2).
  Các trường đó đặt ở ngoài detail, hoặc "image" thay "target", cũng được.
  Cũng đọc được errors.json/rules.json để xem lỗi luật (bỏ qua scene_*).
  Ứng viên cùng (ảnh, loại) được gộp thành một hình; mọi ứng viên của một ảnh giao cho cùng một người.
  Có rules.json cạnh candidates.json (hoặc --rules) thì lỗi luật của ảnh được in lên tiêu đề.

Mỗi ảnh ra một file PNG:
  hàng 1: trái = box detection (vàng, "idx:lớp"), phải = viền segment panoptic (xanh, "s#:lớp")
  hàng 2: (khi có vật bị nghi) vùng cắt quanh vật, phóng to: trái = cả hai nguồn chồng lên, phải = ảnh gốc
  màu đỏ = box/segment bị nghi; hồng = segment crowd; xám = stuff (chỉ vẽ khi có --stuff)
và một file .txt liệt kê box, segment, và % pixel của mỗi segment nằm trong box (cùng lớp / bất kỳ).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DET = (255, 210, 0)
SEG = (0, 220, 255)
STUFF = (160, 160, 160)
CROWD = (255, 140, 200)
HL = (255, 40, 40)
BG = (30, 30, 30)
PANEL = 640        # cạnh dài tối thiểu mỗi khung; ảnh nhỏ (vd 240x320) được phóng to
CROP_H = 420       # chiều cao vùng cắt phóng to
GAP = 8


def _font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf", "Arial.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


F_LABEL = _font(14)
F_HEAD = _font(16)


# ---------------------------------------------------------------- đọc delivery

class Delivery:
    def __init__(self, root: Path):
        self.root = root
        self.classes: dict[int, str] = {}
        for line in (root / "classes.txt").read_text(encoding="utf-8").splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[0].lstrip("-").isdigit():
                self.classes[int(parts[0])] = parts[1]
        pan = json.loads((root / "panoptic.json").read_text(encoding="utf-8"))
        self.cats = {c["id"]: c for c in pan.get("categories", [])}
        infos = {im["id"]: im for im in pan.get("images", [])}
        self.pan: dict[str, tuple[dict, dict]] = {}
        for ann in pan.get("annotations", []):
            self.pan[Path(ann["file_name"]).stem] = (ann, infos.get(ann.get("image_id"), {}))
        self.items: dict[str, dict] = {}
        if (root / "manifest.json").is_file():
            self.items = json.loads((root / "manifest.json").read_text(encoding="utf-8")).get("items", {})
        self.meta: dict[str, dict] = {}
        if (root / "metadata.json").is_file():
            for row in json.loads((root / "metadata.json").read_text(encoding="utf-8")).get("items", []):
                self.meta[str(row.get("image"))] = row

    def names(self) -> list[str]:
        found = set(self.items) | set(self.pan) | {p.stem for p in (self.root / "images").glob("*.jpg")}
        return sorted(found)

    def _path(self, stem: str, key: str, default: str) -> Path:
        rel = self.items.get(stem, {}).get(key) or default
        return self.root / rel

    def image_path(self, stem: str) -> Path:
        return self._path(stem, "image", f"images/{stem}.jpg")

    def label_path(self, stem: str) -> Path:
        return self._path(stem, "label", f"labels/{stem}.txt")

    def mask_path(self, stem: str) -> Path:
        ann = self.pan.get(stem, ({}, {}))[0]
        return self._path(stem, "mask", f"masks/{ann.get('file_name', stem + '.png')}")


def read_boxes(d: Delivery, stem: str, W: int, H: int) -> list[dict]:
    path = d.label_path(stem)
    if not path.is_file():
        return []
    boxes = []
    # idx = số dòng vật lý, đếm từ 1, bỏ dòng trống (khớp validate.py label_rows)
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        f = line.split()
        try:
            cid = int(float(f[0]))
            xc, yc, w, h = (float(v) for v in f[1:5])
        except (ValueError, IndexError):
            boxes.append({"idx": i, "bad": line})
            continue
        x0, x1 = sorted(((xc - w / 2) * W, (xc + w / 2) * W))
        y0, y1 = sorted(((yc - h / 2) * H, (yc + h / 2) * H))
        boxes.append({"idx": i, "cid": cid, "name": d.classes.get(cid, f"?{cid}"), "xyxy": (x0, y0, x1, y1)})
    return boxes


def _lut(value: int) -> list[int]:
    return [255 if i == value else 0 for i in range(256)]


def segment_masks(mask: Image.Image, segs: list[dict]) -> dict[int, Image.Image]:
    """Mặt nạ nhị phân (L, 0/255) cho từng segment: id = R + G*256 + B*256^2."""
    R, G, B = mask.split()
    out = {}
    for sg in segs:
        sid = int(sg["id"])
        m = ImageChops.multiply(R.point(_lut(sid & 255)), G.point(_lut((sid >> 8) & 255)))
        out[sid] = ImageChops.multiply(m, B.point(_lut((sid >> 16) & 255)))
    return out


def pixels_inside(m: Image.Image, xyxy, W: int, H: int) -> int:
    x0, y0, x1, y1 = xyxy
    box = (max(0, int(round(x0))), max(0, int(round(y0))), min(W, int(round(x1))), min(H, int(round(y1))))
    if box[2] <= box[0] or box[3] <= box[1]:
        return 0
    return m.crop(box).histogram()[255]


# ---------------------------------------------------------------- vẽ

def tag(dr: ImageDraw.ImageDraw, xy, text: str, color, size) -> None:
    l, t, r, b = dr.textbbox((0, 0), text, font=F_LABEL)
    w, h = r - l + 6, b - t + 4
    x, y = xy
    y = y - h if y - h >= 0 else y
    x = min(max(0, x), size[0] - w)
    y = min(max(0, y), size[1] - h)
    dr.rectangle((x, y, x + w, y + h), fill=color)
    dr.text((x + 3 - l, y + 2 - t), text, fill=(0, 0, 0), font=F_LABEL)


def _overlaps(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def draw_boxes(canvas: Image.Image, boxes: list[dict], hl: set[int], s: float, region=None) -> None:
    """Vẽ box lên canvas; canvas = ảnh gốc (hoặc vùng `region` của ảnh gốc) phóng theo hệ số s."""
    ox, oy = (region[0], region[1]) if region else (0, 0)
    dr = ImageDraw.Draw(canvas)
    ok = [b for b in boxes if "bad" not in b and (region is None or _overlaps(b["xyxy"], region))]
    ok.sort(key=lambda b: b["idx"] in hl)                      # box bị nghi vẽ sau cùng
    for b in ok:
        x0, y0, x1, y1 = b["xyxy"]
        is_hl = b["idx"] in hl
        dr.rectangle(((x0 - ox) * s, (y0 - oy) * s, (x1 - ox) * s, (y1 - oy) * s),
                     outline=HL if is_hl else DET, width=4 if is_hl else 2)
    for b in ok:
        tag(dr, ((b["xyxy"][0] - ox) * s, (b["xyxy"][1] - oy) * s), f"{b['idx']}:{b['name']}",
            HL if b["idx"] in hl else DET, canvas.size)


def draw_segments(canvas: Image.Image, rows: list[dict], hl: set[int], s: float, show_stuff: bool, region=None) -> None:
    """Tô viền segment; với `region` (pixel ảnh gốc) thì chỉ vẽ phần nằm trong vùng đó."""
    ox, oy = (region[0], region[1]) if region else (0, 0)
    labels = []
    for r in sorted(rows, key=lambda r: r["id"] in hl):
        if r["m"] is None or not r["px"]:
            continue
        is_hl = r["id"] in hl
        if not r["thing"] and not show_stuff and not is_hl:
            continue
        if region is not None and not _overlaps(r["pbox"], region):
            continue
        m = r["m"].crop(region) if region is not None else r["m"]
        ms = m.resize(canvas.size, Image.NEAREST) if m.size != canvas.size else m
        if is_hl:
            canvas.paste(HL, mask=ms.point(lambda v: 100 if v else 0))
        color = HL if is_hl else CROWD if r["crowd"] else SEG if r["thing"] else STUFF
        edge = ImageChops.subtract(ms.filter(ImageFilter.MaxFilter(5 if is_hl else 3)), ms.filter(ImageFilter.MinFilter(3)))
        canvas.paste(color, mask=edge)
        labels.append((((r["pbox"][0] - ox) * s, (r["pbox"][1] - oy) * s),
                       f"s{r['k']}:{r['name']}" + (" crowd" if r["crowd"] else ""), color))
    dr = ImageDraw.Draw(canvas)
    for xy, text, color in labels:
        tag(dr, xy, text, color, canvas.size)


def fit(im: Image.Image, max_w: int, max_h: int) -> Image.Image:
    f = min(max_w / im.width, max_h / im.height)
    return im.resize((max(1, round(im.width * f)), max(1, round(im.height * f))), Image.LANCZOS)


def render(d: Delivery, stem: str, hl_boxes=(), hl_segs=(), ctype: str = "", reason: str = "",
           show_stuff: bool = False, crop=None, rule_errs=()) -> tuple[Image.Image, str]:
    hl_boxes, hl_segs = set(hl_boxes), set(hl_segs)
    warn: list[str] = []
    if rule_errs:
        warn.append(f"ảnh đã có lỗi luật: {', '.join(sorted(rule_errs))} (mỗi ảnh nhiều nhất một lỗi: ứng viên có thể là hệ quả)")
    ann, info = d.pan.get(stem, (None, {}))
    if ann is None:
        warn.append("ảnh không có trong panoptic.json")

    img = mask = None
    ip = d.image_path(stem)
    if not ip.is_file():
        warn.append(f"THIẾU FILE ẢNH {ip.name} (missing_image?)")
    else:
        try:
            with Image.open(ip) as im:
                img = im.convert("RGB")
        except Exception as exc:  # ảnh hỏng: dấu hiệu wrong_hash do file bị đổi
            warn.append(f"ẢNH KHÔNG MỞ ĐƯỢC: {exc.__class__.__name__}")
    mp = d.mask_path(stem)
    if mp.is_file():
        try:
            with Image.open(mp) as im:
                mask = im.convert("RGB")
        except Exception as exc:
            warn.append(f"mask không mở được: {exc.__class__.__name__}")
    else:
        warn.append("thiếu mask")
    size = (img or mask).size if (img or mask) else (info.get("width", 640), info.get("height", 480))
    if img is None:
        img = Image.new("RGB", size, (90, 90, 90))
    if mask is not None and mask.size != img.size:
        warn.append(f"mask {mask.size} khác cỡ ảnh {img.size}, đã co giãn")
        mask = mask.resize(img.size, Image.NEAREST)
    W, H = img.size

    boxes = read_boxes(d, stem, W, H)
    bad = [b for b in boxes if "bad" in b]
    if bad:
        warn.append(f"{len(bad)} dòng nhãn không đọc được")
    if not d.label_path(stem).is_file():
        warn.append("thiếu file nhãn")
    segs = ann.get("segments_info", []) if ann else []
    bins = segment_masks(mask, segs) if mask is not None else {}

    rows = []
    for k, sg in enumerate(segs):
        cat = d.cats.get(sg.get("category_id"))
        m = bins.get(int(sg["id"]))
        px = m.histogram()[255] if m is not None else 0
        rows.append({
            "k": k, "id": int(sg["id"]), "cid": sg.get("category_id"),
            "name": cat["name"] if cat else f"?{sg.get('category_id')}",
            "thing": (cat.get("isthing", 1) == 1) if cat else True,
            "crowd": bool(sg.get("iscrowd")), "area": sg.get("area"), "px": px,
            "pbox": m.getbbox() if (m is not None and px) else None, "m": m,
        })
    known = {r["id"] for r in rows}
    for sid in hl_segs - known:
        warn.append(f"segment_id {sid} không có trong segments_info")
    for bi in hl_boxes - {b["idx"] for b in boxes}:
        warn.append(f"box_idx {bi} không có trong file nhãn")

    # khung chính
    s = max(1.0, PANEL / max(W, H))
    SW, SH = round(W * s), round(H * s)
    base = img.resize((SW, SH), Image.LANCZOS) if s != 1 else img.copy()
    det = base.copy()
    draw_boxes(det, boxes, hl_boxes, s)
    pan = base.copy()
    draw_segments(pan, rows, hl_segs, s, show_stuff)

    # vùng cắt quanh vật bị nghi
    rects = [b["xyxy"] for b in boxes if "bad" not in b and b["idx"] in hl_boxes]
    rects += [r["pbox"] for r in rows if r["id"] in hl_segs and r["pbox"]]
    if crop:
        rects.append(crop)
    crops = None
    if rects:
        x0 = min(r[0] for r in rects); y0 = min(r[1] for r in rects)
        x1 = max(r[2] for r in rects); y1 = max(r[3] for r in rects)
        mx, my = max(20, 0.35 * (x1 - x0)), max(20, 0.35 * (y1 - y0))
        region = (int(max(0, x0 - mx)), int(max(0, y0 - my)), int(min(W, x1 + mx + 1)), int(min(H, y1 + my + 1)))
        if region[2] - region[0] >= 2 and region[3] - region[1] >= 2:
            raw = fit(img.crop(region), SW, CROP_H)               # phóng từ ảnh gốc, nét hơn
            f = raw.width / (region[2] - region[0])
            both = raw.copy()
            draw_segments(both, rows, hl_segs, f, show_stuff, region)
            draw_boxes(both, boxes, hl_boxes, f, region)
            crops = (both, raw)

    # ghép
    meta = d.meta.get(stem, {})
    head = [f"{stem}   {W}x{H}   scene={meta.get('scene_id', '?')}  split={meta.get('split', '?')}  "
            f"job={meta.get('job_id', '?')}  guideline(ảnh)={meta.get('guideline_version', '?')}   "
            f"{len(boxes)} box / {sum(r['thing'] for r in rows)} thing / {len(rows)} segment"]
    if ctype or reason:
        head.append(f"Ứng viên: {ctype}   {reason}".rstrip())
    head += [f"! {w}" for w in warn]
    head.append("vàng = box detection (idx:lớp)   xanh = viền segment thing (s#:lớp)   hồng = crowd   đỏ = bị nghi")
    line_h = 22
    head_h = GAP + line_h * len(head)
    cap_h = 22
    width = SW * 2 + GAP * 3
    height = head_h + cap_h + SH + GAP
    if crops:
        height += cap_h + max(c.height for c in crops) + GAP
    out = Image.new("RGB", (width, height), BG)
    dr = ImageDraw.Draw(out)
    y = GAP
    for i, text in enumerate(head):
        color = (255, 120, 120) if text.startswith("!") else (255, 230, 120) if text.startswith("Ứng viên") else (235, 235, 235)
        dr.text((GAP, y), text, fill=color, font=F_HEAD)
        y += line_h
    dr.text((GAP, y), "DETECTION  labels/", fill=DET, font=F_HEAD)
    dr.text((SW + GAP * 2, y), "PANOPTIC  masks/ + panoptic.json", fill=SEG, font=F_HEAD)
    y += cap_h
    out.paste(det, (GAP, y))
    out.paste(pan, (SW + GAP * 2, y))
    y += SH + GAP
    if crops:
        dr.text((GAP, y), "PHÓNG TO: hai nguồn chồng lên", fill=(235, 235, 235), font=F_HEAD)
        dr.text((SW + GAP * 2, y), "PHÓNG TO: ảnh gốc (nhìn vật)", fill=(235, 235, 235), font=F_HEAD)
        y += cap_h
        out.paste(crops[0], (GAP, y))
        out.paste(crops[1], (SW + GAP * 2, y))

    return out, summary(stem, W, H, meta, warn, ctype, reason, boxes, rows)


def summary(stem, W, H, meta, warn, ctype, reason, boxes, rows) -> str:
    L = [f"ẢNH {stem}  {W}x{H}  scene={meta.get('scene_id', '?')} split={meta.get('split', '?')} "
         f"job={meta.get('job_id', '?')} guideline(ảnh)={meta.get('guideline_version', '?')}"]
    if ctype or reason:
        L.append(f"Ứng viên: {ctype} {reason}".rstrip())
    L += [f"! {w}" for w in warn]
    L.append("")
    L.append(f"DETECTION: {len(boxes)} box (pixel)")
    L.append(f"{'idx':>4}  {'lớp':<16}{'x0':>7}{'y0':>7}{'x1':>7}{'y1':>7}{'w':>7}{'h':>7}")
    for b in boxes:
        if "bad" in b:
            L.append(f"{b['idx']:>4}  KHÔNG ĐỌC ĐƯỢC: {b['bad']}")
            continue
        x0, y0, x1, y1 = b["xyxy"]
        L.append(f"{b['idx']:>4}  {b['cid']:>2} {b['name']:<13}{x0:7.0f}{y0:7.0f}{x1:7.0f}{y1:7.0f}{x1 - x0:7.0f}{y1 - y0:7.0f}")
    L.append("")
    L.append(f"PANOPTIC: {len(rows)} segment. %trong = % pixel của segment nằm trong box")
    L.append(f"{'s#':>4}  {'id':>9}  {'lớp':<18}{'loại':<7}{'area':>7}{'pixel':>7}   box cùng lớp tốt nhất   box bất kỳ tốt nhất")
    ok = [b for b in boxes if "bad" not in b]
    for r in rows:
        kind = "crowd" if r["crowd"] else "thing" if r["thing"] else "stuff"
        line = f"{r['k']:>4}  {r['id']:>9}  {r['name'][:17]:<18}{kind:<7}{str(r['area']):>7}{r['px']:>7}"
        if r["thing"] and r["px"] and r["m"] is not None:
            cover = [(pixels_inside(r["m"], b["xyxy"], W, H) / r["px"], b) for b in ok]
            same = [c for c in cover if c[1]["name"] == r["name"]]
            bs = max(same, key=lambda c: c[0]) if same else None
            ba = max(cover, key=lambda c: c[0]) if cover else None
            same_txt = f"{bs[0]:4.0%} (box {bs[1]['idx']})" if bs else "KHÔNG CÓ"
            any_txt = f"{ba[0]:4.0%} (box {ba[1]['idx']}:{ba[1]['name']})" if ba else "-"
            line += f"   {same_txt:<22}{any_txt}"
        L.append(line)
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- hàng đợi

def as_list(v) -> list[int]:
    if v is None or v == "":
        return []
    if isinstance(v, (list, tuple)):
        return [int(x) for x in v]
    return [int(v)]


def _fmt(v) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def describe(det: dict) -> str:
    """Một dòng lý do từ detail của validator."""
    if det.get("reason"):
        return str(det["reason"])
    parts = []
    if det.get("det_class") or det.get("pan_class"):
        parts.append(f"detection={det.get('det_class', '-')} / panoptic={det.get('pan_class', '-')}")
    for k, v in det.items():
        if k in ("det_class", "pan_class", "need_review", "segment_id", "box_idx", "label_line", "boxes") \
                or isinstance(v, (list, dict)):
            continue
        parts.append(f"{k}={_fmt(v)}")
    if det.get("need_review"):
        parts.append(str(det["need_review"]))
    return ", ".join(parts)


def load_queue(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    items = data if isinstance(data, list) else (data.get("candidates") or data.get("errors") or [])
    grouped: dict[tuple[str, str], dict] = {}
    for c in items:
        image = str(c.get("image") or c.get("target") or "")
        if not image or image.startswith("scene_"):
            continue
        det = c.get("detail") if isinstance(c.get("detail"), dict) else {}
        src = {**det, **{k: v for k, v in c.items() if k != "detail"}}
        boxes = as_list(src.get("box_idx")) + as_list(src.get("label_line")) + as_list(src.get("boxes"))
        reason = str(c.get("reason") or c.get("note") or describe(det) or "")
        key = (Path(image).stem, str(c.get("type", "")))
        g = grouped.setdefault(key, {"image": key[0], "type": key[1], "boxes": [], "segs": [], "reasons": []})
        g["boxes"] += [b for b in boxes if b not in g["boxes"]]
        g["segs"] += [s for s in as_list(src.get("segment_id")) if s not in g["segs"]]
        if reason and reason not in g["reasons"]:
            g["reasons"].append(reason)
    queue = []
    for g in grouped.values():
        g["reason"] = " | ".join(g.pop("reasons"))
        queue.append(g)
    queue.sort(key=lambda q: (q["type"], q["image"]))
    return queue


def assign(queue: list[dict], people: list[str]) -> list[str]:
    """Chia theo ẢNH (mọi ứng viên của một ảnh về cùng một người), liền khối theo thứ tự đã sắp,
    số ảnh mỗi người chênh nhau tối đa 1."""
    images: list[str] = []
    for q in queue:
        if q["image"] not in images:
            images.append(q["image"])
    owner: dict[str, str] = {}
    start = 0
    for i, person in enumerate(people):
        size = len(images) // len(people) + (1 if i < len(images) % len(people) else 0)
        for img in images[start:start + size]:
            owner[img] = person
        start += size
    return [owner[q["image"]] for q in queue]


def load_rule_errors(path: Path | None) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    if path is None or not path.is_file():
        return out
    for e in json.loads(path.read_text(encoding="utf-8-sig")).get("errors", []):
        if not str(e.get("target", "")).startswith("scene_") and e.get("type"):
            out.setdefault(str(e["target"]), set()).add(str(e["type"]))
        det = e.get("detail") or {}
        if e.get("type") == "scene_leak" and isinstance(det, dict):
            for img in det.get("odd_images", []):
                out.setdefault(str(img), set()).add("scene_leak")
    return out


def default_out(delivery: Path) -> Path:
    parent = delivery.resolve().parent
    return ROOT / "runs" / "view" / ("de_an" if parent == ROOT else parent.name)


def parse_crop(text: str | None):
    if not text:
        return None
    vals = [float(v) for v in text.split(",")]
    if len(vals) != 4:
        raise SystemExit("--crop cần dạng x0,y0,x1,y1")
    return tuple(vals)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Vẽ box detection + viền segment panoptic để review")
    ap.add_argument("delivery", help="thư mục delivery (chỉ đọc)")
    ap.add_argument("images", nargs="*", help="tên ảnh (có hoặc không đuôi)")
    ap.add_argument("--candidates", help="candidates.json hoặc errors.json: vẽ cả hàng đợi")
    ap.add_argument("--all", action="store_true", help="vẽ mọi ảnh trong lô")
    ap.add_argument("--box", type=int, action="append", default=[], help="tô đỏ box idx (lặp được)")
    ap.add_argument("--seg", type=int, action="append", default=[], help="tô đỏ segment id (lặp được)")
    ap.add_argument("--crop", help="vùng phóng to x0,y0,x1,y1 theo pixel ảnh gốc")
    ap.add_argument("--type", default="", help="ghi loại lỗi lên tiêu đề (chế độ từng ảnh)")
    ap.add_argument("--stuff", action="store_true", help="vẽ cả viền segment stuff")
    ap.add_argument("--people", help="TV1,TV2,...: chia hàng đợi theo ảnh, ghi review_<người>.csv")
    ap.add_argument("--rules", help="rules.json của validator (mặc định: rules.json cạnh candidates.json)")
    ap.add_argument("--out", help="thư mục ghi ảnh (mặc định runs/view/<tên lô>)")
    ap.add_argument("--open", action="store_true", help="mở ảnh vừa vẽ (chế độ từng ảnh)")
    args = ap.parse_args()

    delivery = Path(args.delivery)
    if not (delivery / "panoptic.json").is_file():
        raise SystemExit(f"{delivery} không phải thư mục delivery (thiếu panoptic.json)")
    out = Path(args.out) if args.out else default_out(delivery)
    if out.resolve() == delivery.resolve() or delivery.resolve() in out.resolve().parents:
        raise SystemExit("không ghi vào trong delivery: chọn --out khác")
    out.mkdir(parents=True, exist_ok=True)
    d = Delivery(delivery)
    crop = parse_crop(args.crop)

    rules_path = Path(args.rules) if args.rules else (
        Path(args.candidates).parent / "rules.json" if args.candidates else None)
    rule_errs = load_rule_errors(rules_path)
    if rule_errs:
        print(f"lỗi luật lấy từ {rules_path}")

    if args.candidates:
        queue = load_queue(Path(args.candidates))
        if not queue:
            raise SystemExit("hàng đợi rỗng")
        people = [p.strip() for p in args.people.split(",") if p.strip()] if args.people else []
        who = assign(queue, people) if people else [""] * len(queue)
        rows = []
        for i, (q, person) in enumerate(zip(queue, who), start=1):
            name = f"{i:03d}_{q['type'] or 'x'}_{q['image']}"
            im, txt = render(d, q["image"], q["boxes"], q["segs"], q["type"], q["reason"], args.stuff,
                             rule_errs=rule_errs.get(q["image"], ()))
            im.save(out / f"{name}.png")
            (out / f"{name}.txt").write_text(txt, encoding="utf-8")
            rows.append({"order": i, "image": q["image"], "type": q["type"], "reason": q["reason"],
                         "assignee": person, "png": f"{name}.png"})
            print(f"[{i}/{len(queue)}] {name}.png {('-> ' + person) if person else ''}", flush=True)
        with open(out / "queue.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["order", "image", "type", "reason", "assignee", "png"])
            w.writeheader()
            w.writerows(rows)
        for person in people:
            mine = [r for r in rows if r["assignee"] == person]
            with open(out / f"review_{person}.csv", "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["image", "type", "verdict", "note"])
                for r in mine:
                    w.writerow([r["image"], r["type"], "", ""])
            print(f"{person}: {len(mine)} ảnh -> review_{person}.csv")
        print(f"Đã vẽ {len(rows)} ứng viên vào {out}  (danh sách: queue.csv)")
        return 0

    stems = d.names() if args.all else [Path(x).stem for x in args.images]
    if not stems:
        ap.error("cần tên ảnh, --candidates hoặc --all")
    for stem in stems:
        im, txt = render(d, stem, args.box, args.seg, args.type, "", args.stuff, crop,
                         rule_errs=rule_errs.get(stem, ()))
        png = out / f"{stem}.png"
        im.save(png)
        (out / f"{stem}.txt").write_text(txt, encoding="utf-8")
        if len(stems) <= 3:
            print(txt)
        print(f"-> {png}")
        if args.open and len(stems) <= 5 and hasattr(os, "startfile"):
            os.startfile(png)  # type: ignore[attr-defined]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

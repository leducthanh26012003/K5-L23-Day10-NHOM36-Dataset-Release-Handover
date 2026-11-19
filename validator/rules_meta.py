"""TV1 — luật về file và metadata: missing_image, wrong_hash, scene_leak, guideline_mismatch.

Chỉ đọc qua đối tượng `Delivery` (validate.py); không đọc gì ngoài thư mục delivery.

- missing_image      : manifest ghi ảnh nhưng file ảnh không có trong delivery.
- wrong_hash         : sha256 TÍNH LẠI trên bytes của file (đọc 'rb') khác sha256 ghi trong manifest.
                       Kiểm cả ảnh, nhãn và mask; định dạng 64 ký tự hợp lệ không có nghĩa là đúng.
- scene_leak         : một scene_id có ảnh ở cả train và val. target = scene_id; detail ghi ảnh lệch split
                       (split thiểu số trong cảnh) để người làm v2 biết đưa ảnh nào về.
- guideline_mismatch : guideline_version của ảnh (metadata) khác guideline ghi ở JOB của nó (jobs.csv).
"""
from __future__ import annotations

import hashlib
from collections import defaultdict


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _err(type_: str, target: str, **detail) -> dict:
    e = {"type": type_, "target": target}
    if detail:
        e["detail"] = detail
    return e


def missing_and_hash(d) -> list[dict]:
    out = []
    for name in sorted(d.manifest):
        item = d.manifest[name]
        img_rel = item.get("image", f"images/{name}.jpg")
        img = d.path(img_rel)
        if not img.is_file():
            out.append(_err("missing_image", name, file=img_rel))
            continue
        bad = []
        for key, rel in (("image_sha256", img_rel), ("label_sha256", item.get("label")), ("mask_sha256", item.get("mask"))):
            want = (item.get(key) or "").strip().lower()
            if not want or not rel:
                continue
            p = d.path(rel)
            if p.is_file() and _sha256(p) != want:
                bad.append(rel)
        if bad:
            out.append(_err("wrong_hash", name, files=bad))
    return out


def scene_leak(d) -> list[dict]:
    by_scene = defaultdict(lambda: defaultdict(list))
    for name, m in d.meta.items():
        scene, split = m.get("scene_id"), (m.get("split") or "").strip()
        if scene and split:
            by_scene[scene][split].append(name)
    out = []
    for scene in sorted(by_scene):
        splits = by_scene[scene]
        if len(splits) > 1:
            majority = max(splits, key=lambda s: (len(splits[s]), s))
            odd = sorted(n for s, names in splits.items() if s != majority for n in names)
            out.append(_err("scene_leak", scene, splits={s: len(v) for s, v in sorted(splits.items())},
                            majority=majority, odd_images=odd))
    return out


def guideline_mismatch(d) -> list[dict]:
    out = []
    for name in sorted(d.meta):
        m = d.meta[name]
        job = d.jobs.get((m.get("job_id") or "").strip())
        if job is None:
            continue                      # job không có trong jobs.csv: không đủ căn cứ, không báo
        want = (job.get("guideline") or "").strip()
        got = (m.get("guideline_version") or "").strip()
        if want and got != want:
            out.append(_err("guideline_mismatch", name, job=job["job_id"], job_guideline=want, image_guideline=got))
    return out


def check(d) -> list[dict]:
    return missing_and_hash(d) + scene_leak(d) + guideline_mismatch(d)

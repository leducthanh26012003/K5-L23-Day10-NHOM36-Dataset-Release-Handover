#!/usr/bin/env python3
"""Validator của nhóm — khung chung (TV1).

    python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]

Chỉ đọc thư mục delivery được truyền vào, chỉ dùng thư viện chuẩn, không dùng mạng.
Không đọc `_private/`, `data_source/`, annotation COCO. Không ghi cứng tên ảnh / id của seed nào.

Cách ghép phần của từng người (mỗi module là một file trong `validator/`):

| module           | người | hàm                           | trả về                                              |
|------------------|-------|-------------------------------|-----------------------------------------------------|
| `rules_meta.py`  | TV1   | `check(d) -> list[dict]`      | missing_image, wrong_hash, scene_leak, guideline_mismatch |
| `common.py`      | TV2   | (hàm dùng chung)              | đọc mask panoptic, đổi box YOLO sang pixel…          |
| `rules_label.py` | TV2   | `check(d) -> list[dict]`      | invalid_class, bbox_out_of_bounds, duplicate_box, invalid_category_id, thing_overlap |
| `cross_check.py` | TV3   | `match(d, name)` + `candidates(d) -> list[dict]` | ghép box ↔ segment; ứng viên class_swap / category_swap, missing_box |
| `cross_drift.py` | TV6   | `candidates(d) -> list[dict]` | ứng viên bbox_drift, instance_merge (dùng `cross_check.match`) |

Mỗi phần tử là `{"type": ..., "target": ..., "detail": {...}}` (`detail` tuỳ chọn, chỉ để người đọc).
Module chưa có thì bị bỏ qua (in cảnh báo), để mỗi người chạy được phần của mình trước khi ghép.
`d` là đối tượng `Delivery` bên dưới: đọc sẵn manifest, metadata, jobs, classes; panoptic đọc khi cần.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

RULE_MODULES = ["rules_meta", "rules_label"]
CANDIDATE_MODULES = ["cross_check", "cross_drift"]

# Mỗi ảnh mang nhiều nhất một lỗi (docs/DELIVERY.md mục 2). Nếu một ảnh dính nhiều luật, giữ loại đứng trước:
# lỗi file trước (có file mới kiểm được nhãn), rồi lỗi nhãn detection, rồi metadata, cuối cùng là panoptic.
PRIORITY = ["missing_image", "wrong_hash", "invalid_class", "bbox_out_of_bounds", "duplicate_box",
            "guideline_mismatch", "invalid_category_id", "thing_overlap"]
SCENE_TYPES = {"scene_leak"}          # target là scene_id, không phải tên ảnh


def _read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class Delivery:
    """Một lô bàn giao v1: chỉ đọc, không bao giờ ghi vào thư mục này."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        man = _read_json(self.root / "manifest.json", {}) or {}
        self.manifest: dict[str, dict] = man.get("items", {}) if isinstance(man, dict) else {}
        meta = _read_json(self.root / "metadata.json", {}) or {}
        items = meta.get("items", []) if isinstance(meta, dict) else []
        self.meta: dict[str, dict] = {m["image"]: m for m in items if isinstance(m, dict) and "image" in m}
        self.jobs: dict[str, dict] = {}
        jobs_path = self.root / "jobs.csv"
        if jobs_path.exists():
            with jobs_path.open(newline="", encoding="utf-8") as f:
                self.jobs = {r["job_id"].strip(): r for r in csv.DictReader(f) if r.get("job_id")}
        self.classes: dict[int, str] = {}
        cls_path = self.root / "classes.txt"
        if cls_path.exists():
            for line in cls_path.read_text(encoding="utf-8").splitlines():
                parts = line.split(maxsplit=1)
                if len(parts) == 2 and parts[0].lstrip("-").isdigit():
                    self.classes[int(parts[0])] = parts[1].strip()
        rel = _read_json(self.root / "release.json", {}) or {}
        self.release_id = rel.get("release_id", "") if isinstance(rel, dict) else ""
        self._panoptic = None

    # --- tên ảnh: hợp của manifest và metadata, sắp xếp để kết quả ổn định
    def names(self) -> list[str]:
        return sorted(set(self.manifest) | set(self.meta))

    def path(self, rel: str) -> Path:
        return self.root / rel

    def label_rows(self, name: str) -> list[tuple[int, list[str]]] | None:
        """[(số dòng từ 1, các cột)] của file nhãn YOLO, bỏ dòng trống; None nếu không có file."""
        rel = self.manifest.get(name, {}).get("label", f"labels/{name}.txt")
        p = self.root / rel
        if not p.exists():
            return None
        return [(i, ln.split()) for i, ln in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
                if ln.strip()]

    @property
    def panoptic(self) -> dict:
        if self._panoptic is None:
            self._panoptic = _read_json(self.root / "panoptic.json", {}) or {}
        return self._panoptic


def _load(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        if e.name == module_name:
            print(f"[cảnh báo] chưa có validator/{module_name}.py: bỏ qua", file=sys.stderr)
            return None
        raise


def _one_per_image(errors: list[dict]) -> list[dict]:
    """Bỏ trùng (type, target); mỗi ảnh giữ một lỗi theo PRIORITY. Lỗi cấp cảnh (scene_leak) giữ nguyên."""
    seen, by_image, scene = set(), {}, []
    rank = {t: i for i, t in enumerate(PRIORITY)}
    for e in errors:
        key = (e["type"], e["target"])
        if key in seen:
            continue
        seen.add(key)
        if e["type"] in SCENE_TYPES:
            scene.append(e)
            continue
        old = by_image.get(e["target"])
        if old is None or rank.get(e["type"], len(rank)) < rank.get(old["type"], len(rank)):
            if old is not None:
                print(f"[gộp] {e['target']}: giữ {e['type']}, bỏ {old['type']}", file=sys.stderr)
            by_image[e["target"]] = e
        else:
            print(f"[gộp] {e['target']}: giữ {old['type']}, bỏ {e['type']}", file=sys.stderr)
    return sorted(scene + list(by_image.values()), key=lambda e: (e["type"], e["target"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validator lô bàn giao (chỉ đọc delivery/, thư viện chuẩn)")
    ap.add_argument("delivery")
    ap.add_argument("--out", required=True, help="errors.json: lỗi luật (lỗi gán nhãn lấy từ review_log qua merge_review.py)")
    ap.add_argument("--candidates", help="candidates.json: ứng viên lỗi gán nhãn cho người xem ảnh")
    args = ap.parse_args(argv)

    d = Delivery(args.delivery)
    if not d.manifest and not d.meta:
        print(f"không đọc được manifest.json / metadata.json trong {d.root}", file=sys.stderr)
        return 2

    errors = []
    for name in RULE_MODULES:
        mod = _load(name)
        if mod is not None:
            found = mod.check(d)
            print(f"{name}: {len(found)} lỗi", file=sys.stderr)
            errors += found
    errors = _one_per_image(errors)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"errors": errors}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    counts = {}
    for e in errors:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    print(f"đã quét {len(d.names())} ảnh; {len(errors)} lỗi luật {counts} -> {out}", file=sys.stderr)

    if args.candidates:
        cands, seen = [], set()
        for name in CANDIDATE_MODULES:
            mod = _load(name)
            if mod is None:
                continue
            found = mod.candidates(d)
            print(f"{name}: {len(found)} ứng viên", file=sys.stderr)
            for c in found:                    # bỏ trùng (type, target) giữa hai module
                if (c["type"], c["target"]) not in seen:
                    seen.add((c["type"], c["target"]))
                    cands.append(c)
        cands.sort(key=lambda c: (c["target"], c["type"]))
        cp = Path(args.candidates)
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps({"candidates": cands}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{len(cands)} ứng viên -> {cp}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

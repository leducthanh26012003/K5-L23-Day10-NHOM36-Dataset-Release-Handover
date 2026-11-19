#!/usr/bin/env python3
"""Gộp các file review của từng người thành review_log.csv, kiểm trước H3, rồi gọi merge_review.py.

  # chỉ gộp + kiểm
  python tools/gather_review.py runs/view/r36 --out runs/r36/review_log.csv --candidates runs/r36/candidates.json

  # gộp + kiểm + chốt errors.json (gọi scripts/merge_review.py bản gốc)
  python tools/gather_review.py runs/view/r36 --out runs/r36/review_log.csv --candidates runs/r36/candidates.json \
      --delivery runs/r36/delivery --rules runs/r36/rules.json --errors runs/r36/errors.json

Đầu vào: file .csv, mẫu glob (review_*.csv), hoặc thư mục (lấy mọi review_*.csv trong đó).
Mỗi file có cột image,type,verdict,note. Đọc được file Excel lưu (BOM, dấu ';', mã cp1258).

LỖI (chặn ghi, trừ khi --force):
  - verdict không phải confirmed/rejected (dòng chưa xem)
  - type không phải lỗi gán nhãn (merge_review.py sẽ dừng)
  - note < 20 ký tự                                   (H3)
  - < 70% note khác nhau                              (H3)
  - cùng (ảnh, loại) mà verdict mâu thuẫn
  - một ảnh confirmed hai loại lỗi                    (mỗi ảnh nhiều nhất một lỗi)
  - ảnh không có trong lô (khi có --delivery)
CẢNH BÁO: ứng viên chưa ai xem, không có dòng rejected nào (rubric 4 điểm), note trùng nhau,
  ảnh confirmed lỗi gán nhãn mà cũng có lỗi luật, note quá chung chung.
"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import metrics  # noqa: E402  (chỉ đọc danh sách loại lỗi)

FIELDS = ["image", "type", "verdict", "note"]
VERDICTS = {"confirmed", "rejected"}
VAGUE = {"ok", "có lỗi", "lỗi", "sai", "đúng", "không lỗi", "xác nhận", "confirmed", "rejected", "đúng là lỗi", "không phải lỗi"}


def expand(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            files += sorted(p.glob("review_*.csv"))
        elif any(c in item for c in "*?["):
            files += sorted(Path(x) for x in glob.glob(item))
        elif p.is_file():
            files.append(p)
        else:
            raise SystemExit(f"không thấy {item}")
    seen, out = set(), []
    for f in files:
        if f.resolve() not in seen:
            seen.add(f.resolve())
            out.append(f)
    return out


def read_rows(path: Path, warn: list[str]) -> list[dict]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1258", errors="replace")
        warn.append(f"{path.name}: không phải UTF-8 (Excel lưu kiểu ANSI?), đã đọc bằng cp1258: kiểm lại dấu tiếng Việt")
    first = text.splitlines()[0] if text.strip() else ""
    delim = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    cols = [c.strip().lower() for c in (reader.fieldnames or [])]
    if not set(FIELDS) <= set(cols):
        raise SystemExit(f"{path}: cần cột {','.join(FIELDS)}, đang có {cols}")
    rows = []
    for n, r in enumerate(reader, start=2):
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        if not any(r.get(k) for k in FIELDS):
            continue
        rows.append({
            "image": Path(r["image"]).stem if r["image"] else "",
            "type": r["type"].lower(), "verdict": r["verdict"].lower(), "note": " ".join(r["note"].split()),
            "src": f"{path.name}:{n}",
        })
    return rows


def load_candidates(path: Path) -> list[tuple[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    items = data if isinstance(data, list) else (data.get("candidates") or data.get("errors") or [])
    out = []
    for c in items:
        img = str(c.get("image") or c.get("target") or "")
        if img and not img.startswith("scene_"):
            out.append((Path(img).stem, str(c.get("type", ""))))
    return out


def delivery_images(d: Path) -> set[str]:
    names: set[str] = set()
    if (d / "metadata.json").is_file():
        names |= {str(m["image"]) for m in json.loads((d / "metadata.json").read_text(encoding="utf-8")).get("items", [])}
    if (d / "manifest.json").is_file():
        names |= set(json.loads((d / "manifest.json").read_text(encoding="utf-8")).get("items", {}))
    return names


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Gộp + kiểm review_log.csv, rồi chốt errors.json")
    ap.add_argument("inputs", nargs="+", help="file review .csv, mẫu glob, hoặc thư mục có review_*.csv")
    ap.add_argument("--out", required=True, help="review_log.csv gộp")
    ap.add_argument("--candidates", help="candidates.json: kiểm ứng viên nào chưa ai xem")
    ap.add_argument("--delivery", help="thư mục delivery: kiểm tên ảnh, lấy mẫu số QC")
    ap.add_argument("--rules", help="rules.json của validator: có thì gọi merge_review.py")
    ap.add_argument("--errors", help="errors.json đầu ra của merge_review.py (cần --rules)")
    ap.add_argument("--force", action="store_true", help="vẫn ghi dù còn LỖI")
    args = ap.parse_args()
    if bool(args.rules) != bool(args.errors):
        ap.error("--rules và --errors phải đi cùng nhau")

    errs: list[str] = []
    warn: list[str] = []
    files = expand(args.inputs)
    out_path = Path(args.out)
    rows: list[dict] = []
    for f in files:
        got = read_rows(f, warn)
        print(f"đọc {f}  ({len(got)} dòng)")
        rows += got
    if not rows:
        raise SystemExit("không có dòng review nào")

    # dòng mẫu chưa điền mà cùng (ảnh, loại) đã có người khác điền verdict: bỏ, không tính là mâu thuẫn
    filled = {(r["image"], r["type"]) for r in rows if r["verdict"]}
    blank = [r for r in rows if not r["verdict"] and (r["image"], r["type"]) in filled]
    if blank:
        print(f"(thông tin) bỏ {len(blank)} dòng chưa điền mà người khác đã xem cùng ảnh: "
              + ", ".join(r["src"] for r in blank[:5]))
    rows = [r for r in rows if r["verdict"] or (r["image"], r["type"]) not in filled]

    # từng dòng
    for r in rows:
        if not r["image"]:
            errs.append(f"{r['src']}: thiếu tên ảnh")
        if r["verdict"] not in VERDICTS:
            errs.append(f"{r['src']} {r['image']}: verdict '{r['verdict'] or '(trống)'}' — phải là confirmed hoặc rejected")
        if r["type"] not in metrics.SEMANTIC_TYPES:
            errs.append(f"{r['src']} {r['image']}: type '{r['type']}' không phải lỗi gán nhãn {sorted(metrics.SEMANTIC_TYPES)}")
        if len(r["note"]) < 20:
            errs.append(f"{r['src']} {r['image']}: note {len(r['note'])} ký tự (< 20): \"{r['note']}\"")
        elif r["note"].lower().strip(" .") in VAGUE:
            warn.append(f"{r['src']} {r['image']}: note chung chung, hãy tả thấy gì: \"{r['note']}\"")

    # trùng / mâu thuẫn
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        by_pair[(r["image"], r["type"])].append(r)
    merged: list[dict] = []
    for (img, typ), group in sorted(by_pair.items()):
        verdicts = {g["verdict"] for g in group}
        if len(verdicts) > 1:
            errs.append(f"{img} {typ}: verdict mâu thuẫn " + ", ".join(f"{g['src']}={g['verdict']}" for g in group))
        if len(group) > 1:
            warn.append(f"{img} {typ}: {len(group)} người xem ({', '.join(g['src'] for g in group)}); giữ note dài nhất")
        merged.append(max(group, key=lambda g: len(g["note"])))

    confirmed = [r for r in merged if r["verdict"] == "confirmed"]
    per_image = Counter(r["image"] for r in confirmed)
    for img, n in per_image.items():
        if n > 1:
            kinds = [r["type"] for r in confirmed if r["image"] == img]
            errs.append(f"{img}: confirmed {n} loại {kinds}; mỗi ảnh mang nhiều nhất một lỗi, xem lại ảnh và giữ một")

    notes = [r["note"] for r in merged]
    distinct = len(set(notes))
    if notes and distinct < 0.7 * len(notes):
        errs.append(f"chỉ {distinct}/{len(notes)} note khác nhau (< 70%, H3 FAIL): viết riêng cho từng ảnh")
    for note, n in Counter(notes).items():
        if n > 1:
            warn.append(f"note lặp {n} lần: \"{note[:60]}\"")

    if not any(r["verdict"] == "rejected" for r in merged):
        warn.append("không có dòng rejected nào: rubric chấm 4 điểm cho việc phân biệt lỗi với lệch tự nhiên "
                    "(nếu thật sự không có, REPORT phải giải thích bằng số đo trên lô sạch)")

    n_images = 250
    if args.delivery:
        names = delivery_images(Path(args.delivery))
        if names:
            n_images = len(names)
            for r in merged:
                if r["image"] and r["image"] not in names:
                    errs.append(f"{r['image']}: không có trong lô {args.delivery}")

    if args.candidates:
        cands = load_candidates(Path(args.candidates))
        reviewed = {r["image"] for r in merged}
        todo = sorted({img for img, _ in cands} - reviewed)
        if todo:
            warn.append(f"{len(todo)} ảnh ứng viên chưa ai xem: {', '.join(todo[:10])}{' …' if len(todo) > 10 else ''}")
        extra = sorted(reviewed - {img for img, _ in cands})
        if extra:
            print(f"(thông tin) {len(extra)} ảnh review ngoài danh sách ứng viên: {', '.join(extra[:10])}")

    rule_images: set[str] = set()
    if args.rules:
        raw = Path(args.rules).read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            errs.append(f"{args.rules} có BOM UTF-8: merge_review.py sẽ lỗi, lưu lại dạng UTF-8 không BOM")
        rules = json.loads(raw.decode("utf-8-sig")).get("errors", [])
        rule_images = {e["target"] for e in rules if e.get("type") in metrics.RULE_TYPES}
        sem = [e for e in rules if e.get("type") in metrics.SEMANTIC_TYPES]
        if sem:
            print(f"(thông tin) {len(sem)} lỗi gán nhãn trong {Path(args.rules).name} bị merge_review.py bỏ qua; "
                  "chỉ dòng confirmed trong review_log mới được tính")
        for r in confirmed:
            if r["image"] in rule_images:
                warn.append(f"{r['image']}: confirmed {r['type']} nhưng validator cũng báo lỗi luật ở ảnh này "
                            "(mỗi ảnh nhiều nhất một lỗi: một trong hai có thể là báo thừa)")

    # tóm tắt
    print()
    print(f"Gộp {len(rows)} dòng từ {len(files)} file -> {len(merged)} cặp (ảnh, loại)")
    table = Counter((r["type"], r["verdict"]) for r in merged)
    for typ in sorted({t for t, _ in table}):
        print(f"  {typ:<16} confirmed {table[(typ, 'confirmed')]:>3}   rejected {table[(typ, 'rejected')]:>3}")
    for w in warn:
        print(f"CẢNH BÁO  {w}")
    for e in errs:
        print(f"LỖI       {e}")

    if errs and not args.force:
        print(f"\n{len(errs)} LỖI: chưa ghi {out_path}. Sửa file review rồi chạy lại (hoặc --force để ghi tạm).")
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for r in merged:
            w.writerow([r["image"], r["type"], r["verdict"], r["note"]])
    print(f"\n-> {out_path}  ({len(confirmed)} confirmed, {len(merged) - len(confirmed)} rejected)")

    if args.rules:
        if errs:
            print("Còn LỖI nên không chạy merge_review.py.")
            return 1
        cmd = [sys.executable, str(ROOT / "scripts" / "merge_review.py"),
               "--rules", args.rules, "--review", str(out_path), "--out", args.errors]
        subprocess.run(cmd, check=True)
        total = len(json.loads(Path(args.errors).read_text(encoding="utf-8"))["errors"])
        rate = total / n_images
        print(f"QC v1: {total}/{n_images} = {rate:.1%}  -> {'HOLD (> 2%)' if rate > 0.02 else 'đạt ngưỡng 2%'}")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())

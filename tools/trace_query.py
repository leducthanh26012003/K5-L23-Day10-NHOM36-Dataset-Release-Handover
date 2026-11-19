#!/usr/bin/env python3
"""Truy vết ticket của team AI (Pha 5): tạo trace.json gồm tier_a, tier_b, notify.

  python tools/trace_query.py runs/r36/delivery                 # ghi runs/r36/trace.json
  python tools/trace_query.py delivery                          # đề ẩn: ghi submission/de_an/trace.json
  python tools/trace_query.py runs/r36/delivery --detail runs/r36/trace_detail.csv

Tiêu chí (GUIDE Pha 5, DELIVERY mục 3):
  - "lớp bị đổi quy tắc" (X) và phiên bản đổi (vd v1.3) đọc từ guideline/changelog.md;
    guideline CŨ = mọi phiên bản nhỏ hơn phiên bản đổi.
  - cảnh team AI nêu đọc từ incoming/ticket.md (mọi chuỗi scene_<số>).
  - guideline của ảnh lấy theo JOB: metadata.json -> job_id -> jobs.csv.
    KHÔNG dùng guideline_version ghi ở từng ảnh (có thể chính là lỗi guideline_mismatch).
  - "có lớp X" = có ít nhất một box detection lớp X trong labels/<ảnh>.txt (không dùng panoptic).
  tier_a = ảnh thuộc cảnh trong ticket + job guideline cũ + có box lớp X
  tier_b = các ảnh còn lại thoả cùng điều kiện (job guideline cũ + có box lớp X)
  notify = annotator và reviewer của các job chứa ảnh tier_a hoặc tier_b

Tự đọc sai thì ghi đè bằng --class, --changed-in, --scenes. Chỉ đọc delivery; chỉ thư viện chuẩn.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"v(\d+(?:\.\d+)*)", re.I)


def vkey(text: str) -> tuple[int, ...]:
    m = VERSION.search(text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def parse_changelog(text: str) -> tuple[str | None, str | None]:
    """Trả (tên lớp bị đổi, phiên bản đổi): phiên bản MỚI NHẤT có dòng "Lớp `<tên>`" trong mục của nó."""
    sections: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        head = re.match(r"\s*#{2,}\s*(v\d+(?:\.\d+)*)", line, re.I)
        if head:
            sections.append((head.group(1), []))
        elif sections:
            sections[-1][1].append(line)
    found = []
    for version, lines in sections:
        for line in lines:
            m = re.search(r"[Ll]ớp\s+`([^`]+)`", line)
            if m and not re.search(r"không đổi", line, re.I):
                found.append((vkey(version), version, m.group(1).strip()))
                break
    if not found:
        return None, None
    _, version, name = max(found)
    return name, version


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Truy vết ticket: tier_a, tier_b, notify")
    ap.add_argument("delivery", help="thư mục delivery (chỉ đọc)")
    ap.add_argument("--out", help="trace.json (mặc định: cạnh delivery, đề ẩn thì submission/de_an/trace.json)")
    ap.add_argument("--class", dest="cls", help="ghi đè lớp bị đổi quy tắc (tên trong classes.txt)")
    ap.add_argument("--changed-in", help="ghi đè phiên bản đổi quy tắc, vd v1.3 (cũ = nhỏ hơn bản này)")
    ap.add_argument("--scenes", help="ghi đè danh sách cảnh, vd scene_742,scene_768")
    ap.add_argument("--detail", help="ghi CSV chi tiết từng ảnh có lớp X (để kiểm tay / viết REPORT)")
    args = ap.parse_args()

    d = Path(args.delivery)
    for need in ("jobs.csv", "metadata.json", "classes.txt", "guideline/changelog.md", "incoming/ticket.md"):
        if not (d / need).is_file():
            raise SystemExit(f"thiếu {d / need}")

    # 1. lớp bị đổi quy tắc + phiên bản
    changelog = (d / "guideline" / "changelog.md").read_text(encoding="utf-8")
    cls_name, changed_in = parse_changelog(changelog)
    cls_name = args.cls or cls_name
    changed_in = args.changed_in or changed_in
    if not cls_name or not changed_in:
        raise SystemExit("không đọc được lớp/phiên bản từ changelog.md: dùng --class và --changed-in")

    classes: dict[int, str] = {}
    for line in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            classes[int(parts[0])] = parts[1].strip()
    cls_ids = {i for i, n in classes.items() if n.lower() == cls_name.lower()}
    if not cls_ids:
        raise SystemExit(f"lớp '{cls_name}' không có trong classes.txt")

    # 2. cảnh trong ticket
    ticket = (d / "incoming" / "ticket.md").read_text(encoding="utf-8")
    scenes = [s.strip() for s in args.scenes.split(",")] if args.scenes else sorted(set(re.findall(r"scene_\d+", ticket)))
    if not scenes:
        raise SystemExit("không thấy scene_* trong ticket.md: dùng --scenes")
    ticket_classes = set(re.findall(r"`([^`]+)`", ticket))
    warnings = []
    if ticket_classes and cls_name not in ticket_classes:
        warnings.append(f"ticket nhắc {sorted(ticket_classes)} nhưng changelog đổi '{cls_name}': kiểm lại bằng mắt")

    # 3. job -> guideline, người
    with open(d / "jobs.csv", encoding="utf-8", newline="") as f:
        jobs = {r["job_id"].strip(): {k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)}
    old_jobs = {j for j, r in jobs.items() if vkey(r["guideline"]) < vkey(changed_in)}

    # 4. duyệt ảnh
    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]
    items = {}
    if (d / "manifest.json").is_file():
        items = json.loads((d / "manifest.json").read_text(encoding="utf-8")).get("items", {})
    known_scenes = {str(m.get("scene_id")) for m in meta}
    for s in scenes:
        if s not in known_scenes:
            warnings.append(f"{s} trong ticket không có trong metadata.json")

    tier_a, tier_b, detail = [], [], []
    no_job = []
    for m in meta:
        image = str(m["image"])
        job = str(m.get("job_id", ""))
        if job not in jobs:
            no_job.append(image)
            continue
        label = d / (items.get(image, {}).get("label") or f"labels/{image}.txt")
        n = 0
        if label.is_file():
            for line in label.read_text(encoding="utf-8", errors="replace").splitlines():
                parts = line.split()
                try:
                    if parts and int(float(parts[0])) in cls_ids:
                        n += 1
                except ValueError:
                    continue
        if n == 0:
            continue
        g_job = jobs[job]["guideline"]
        in_ticket = str(m.get("scene_id")) in scenes
        old = job in old_jobs
        tier = ("a" if in_ticket else "b") if old else ""
        if tier == "a":
            tier_a.append(image)
        elif tier == "b":
            tier_b.append(image)
        detail.append({
            "image": image, "scene_id": m.get("scene_id", ""), "job_id": job,
            "guideline_job": g_job, "guideline_anh": m.get("guideline_version", ""),
            f"so_box_{cls_name}": n, "scene_trong_ticket": in_ticket, "tier": tier,
        })
    if no_job:
        warnings.append(f"{len(no_job)} ảnh có job_id không có trong jobs.csv: {no_job[:5]}")

    hit_jobs = sorted({r["job_id"] for r in detail if r["tier"]})
    notify = sorted({jobs[j][k] for j in hit_jobs for k in ("annotator", "reviewer") if jobs[j].get(k)})

    out = Path(args.out) if args.out else (
        ROOT / "submission" / "de_an" / "trace.json" if d.resolve().parent == ROOT else d.resolve().parent / "trace.json")
    if d.resolve() in out.resolve().parents:
        raise SystemExit("không ghi vào trong delivery: chọn --out khác")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"tier_a": sorted(tier_a), "tier_b": sorted(tier_b), "notify": notify},
                              indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.detail:
        with open(args.detail, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(detail[0].keys()) if detail else ["image"])
            w.writeheader()
            w.writerows(detail)

    # 5. in giải thích
    print(f"Lớp bị đổi quy tắc : {cls_name} (class_id {sorted(cls_ids)}), đổi ở {changed_in}")
    print(f"Guideline cũ       : job có guideline < {changed_in}: {', '.join(sorted(old_jobs)) or '(không có)'}")
    print(f"Cảnh trong ticket  : {', '.join(scenes)}")
    print(f"Ảnh có box {cls_name}: {len(detail)} (job cũ: {len(tier_a) + len(tier_b)}, job mới: {len(detail) - len(tier_a) - len(tier_b)})")
    print(f"tier_a ({len(tier_a)}): {', '.join(sorted(tier_a))}")
    print(f"tier_b ({len(tier_b)}): {', '.join(sorted(tier_b))}")
    print(f"Job liên quan      : {', '.join(hit_jobs)}")
    print(f"notify ({len(notify)}): {', '.join(notify)}")
    lech = [r for r in detail if r["guideline_anh"] != r["guideline_job"]]
    if lech:
        print(f"Ảnh có guideline ghi ở ảnh khác job ({len(lech)}), đã lấy theo job:")
        for r in lech:
            print(f"  {r['image']}  job {r['job_id']}={r['guideline_job']}  ảnh={r['guideline_anh']}  tier={r['tier'] or '-'}")
    for w in warnings:
        print(f"! {w}")
    if not tier_a:
        print("! tier_a rỗng: H16 sẽ FAIL, kiểm lại ticket/changelog")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

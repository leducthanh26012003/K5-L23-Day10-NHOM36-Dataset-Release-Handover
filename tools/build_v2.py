#!/usr/bin/env python3
"""Tạo bản nháp bàn giao detection v2; không sửa delivery hoặc ghi lineage.

python3 tools/build_v2.py --run runs/r3007
python3 tools/build_v2.py --run runs/r3007 --hash-reviewed 000000000123

Chỉ dùng --hash-reviewed sau khi người trong nhóm đã mở và kiểm tra ảnh.
Nếu ảnh sai/hỏng, dùng --hash-rework thay thế. Không tự nhận diện ảnh bằng AI.
"""
import argparse
import csv
import hashlib
import json
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

DET_REWORK = {
    "missing_image", "invalid_class", "bbox_out_of_bounds", "duplicate_box",
    "class_swap", "bbox_drift", "missing_box",
}
PANOPTIC = {"invalid_category_id", "thing_overlap", "category_swap", "instance_merge"}
OTHER = {"wrong_hash", "guideline_mismatch", "scene_leak"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def source_file(delivery, relative):
    path = (delivery / relative).resolve()
    if not path.is_relative_to(delivery.resolve()):
        raise ValueError(f"Đường dẫn nằm ngoài delivery: {relative}")
    if not path.is_file():
        raise ValueError(f"Thiếu file đầu vào: {path}")
    return path


def build(args):
    run = Path(args.run).resolve()
    delivery = run / "delivery"
    release_id = read_json(delivery / "release.json")["release_id"]
    if not isinstance(release_id, str) or Path(release_id).name != release_id or release_id in {".", ".."}:
        raise ValueError("release_id không hợp lệ")
    manifest = read_json(delivery / "manifest.json")["items"]
    metadata = {r["image"]: r for r in read_json(delivery / "metadata.json")["items"]}
    errors = read_json(run / "errors.json")["errors"]
    if not manifest or set(manifest) != set(metadata):
        raise ValueError("Manifest rỗng hoặc không khớp metadata")
    with (delivery / "jobs.csv").open(encoding="utf-8", newline="") as f:
        jobs = {r["job_id"]: r for r in csv.DictReader(f)}
    classes = {}
    for line in (delivery / "classes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            idx, name = line.split(maxsplit=1)
            classes[int(idx)] = name.strip()
    scenes = defaultdict(list)
    for image, row in metadata.items():
        scenes[row["scene_id"]].append(image)
        if row["job_id"] not in jobs:
            raise ValueError(f"Không tìm thấy job cho {image}")
    error_pairs = set()
    by_image = defaultdict(set)
    for e in errors:
        kind, target = e["type"], e["target"]
        if kind not in DET_REWORK | PANOPTIC | OTHER:
            raise ValueError(f"Loại lỗi chưa hỗ trợ: {kind}")
        if target not in (scenes if kind == "scene_leak" else manifest):
            raise ValueError(f"Target không hợp lệ: {kind}/{target}")
        if (kind, target) in error_pairs:
            raise ValueError(f"Lỗi lặp trong errors.json: {kind}/{target}")
        error_pairs.add((kind, target))
        if kind != "scene_leak":
            by_image[target].add(kind)

    wrong_hash = {image for image, kinds in by_image.items() if "wrong_hash" in kinds}
    reviewed, hash_rework = set(args.hash_reviewed), set(args.hash_rework)
    if reviewed & hash_rework or (reviewed | hash_rework) - wrong_hash:
        raise ValueError("Xác nhận hash bị trùng hoặc chứa ảnh không có lỗi wrong_hash")
    pending = wrong_hash - reviewed - hash_rework
    if pending:
        raise ValueError("Cần mở ảnh kiểm tra rồi dùng --hash-reviewed hoặc --hash-rework cho: " + ", ".join(sorted(pending)))

    rework = {image for image, kinds in by_image.items() if kinds & DET_REWORK} | hash_rework
    kept = sorted(set(manifest) - rework)
    # Chọn split đa số của cả cảnh v1; nếu hoà, chọn theo thứ tự tên split.
    scene_split = {}
    for scene, images in scenes.items():
        counts = Counter(metadata[image]["split"] for image in images)
        scene_split[scene] = sorted(counts, key=lambda split: (-counts[split], split))[0]

    # Kiểm tra toàn bộ đầu vào trước khi tạo thư mục kết quả.
    sources = {}
    for image in kept:
        if Path(image).name != image or image in {".", ".."}:
            raise ValueError(f"Tên ảnh không hợp lệ: {image}")
        item = manifest[image]
        img = source_file(delivery, item["image"])
        label = source_file(delivery, item["label"])
        if sha(label) != item["label_sha256"]:
            raise ValueError(f"Nhãn v1 đã thay đổi: {image}")
        if sha(img) != item["image_sha256"] and image not in reviewed:
            raise ValueError(f"Hash ảnh lệch nhưng chưa được xác nhận: {image}")
        sources[image] = (img, label)

    parent = run / "handover"
    destination = parent / f"{release_id}_v2"
    if destination.exists():
        raise ValueError(f"Đã có {destination}. Giữ bản cũ để đối chiếu; chuyển nó ra nơi khác trước khi chạy lại.")
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".v2-draft-", dir=parent) as temp:
        folder = Path(temp) / destination.name
        (folder / "images").mkdir(parents=True)
        (folder / "labels").mkdir()
        file_rows, trace_rows = [], []
        counts = Counter()
        for image in kept:
            img, label = sources[image]
            for source, relative in ((img, f"images/{image}.jpg"), (label, f"labels/{image}.txt")):
                target = folder / relative
                shutil.copyfile(source, target)
                file_rows.append({"file": relative, "sha256": sha(target)})
            for line in label.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    parts = line.split()
                    if len(parts) != 5:
                        raise ValueError(f"Dòng YOLO không đủ 5 trường: {image}")
                    numeric_class = float(parts[0])
                    class_id = int(numeric_class)
                    if class_id != numeric_class or class_id not in classes:
                        raise ValueError(f"Lớp không hợp lệ ở ảnh giữ lại: {image}")
                    counts[classes[class_id]] += 1
            meta = metadata[image]
            job = jobs[meta["job_id"]]
            trace_rows.append(dict(image=image, scene_id=meta["scene_id"], split=scene_split[meta["scene_id"]],
                                   job_id=meta["job_id"], annotator=job["annotator"], reviewer=job["reviewer"], guideline=job["guideline"]))
        rework_rows = []
        for image in sorted(rework):
            job = jobs[metadata[image]["job_id"]]
            for kind in sorted(by_image[image] & DET_REWORK | ({"wrong_hash"} if image in hash_rework else set())):
                rework_rows.append(dict(image=image, type=kind, annotator=job["annotator"], reviewer=job["reviewer"],
                                        action="Khôi phục file hoặc gán lại; review và QC trước khi đưa vào release tiếp theo"))
        write_csv(folder / "manifest.csv", ["file", "sha256"], file_rows)
        write_csv(folder / "label_summary.csv", ["class", "count"],
                  [{"class": name, "count": counts[name]} for name in sorted(counts)] + [{"class": "TOTAL", "count": sum(counts.values())}])
        write_csv(folder / "truyvet.csv", ["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"], trace_rows)
        write_csv(folder / "rework_queue.csv", ["image", "type", "annotator", "reviewer", "action"], rework_rows)
        # Khớp cách bộ kiểm gốc đếm target duy nhất; một scene_leak tính một đơn vị.
        bad = len({e["target"] for e in errors})
        rate = bad / len(manifest)
        decision = "Hold" if rate > 0.02 else "Release"
        panoptic_notes = "; ".join(f"{image}: {','.join(sorted(kinds & PANOPTIC))}" for image, kinds in sorted(by_image.items()) if kinds & PANOPTIC) or "không có lỗi panoptic được báo"
        changed_scenes = sorted(scene for scene, images in scenes.items() if len({metadata[i]["split"] for i in images}) > 1)
        guideline_fixes = sorted(image for image in kept if metadata[image]["guideline_version"] != jobs[metadata[image]["job_id"]]["guideline"])
        readme = [
            f"Release: {release_id}_v2", f"Parent: {release_id}", f"Số ảnh: {len(kept)}", f"Số nhãn: {sum(counts.values())}",
            "Guideline: " + "; ".join(f"{j}={jobs[j]['guideline']}" for j in sorted({metadata[i]['job_id'] for i in kept})),
            f"QC v1: {bad}/{len(manifest)} = {rate:.2%}",
            f"Kết luận v1: {decision} — {'trên' if rate > 0.02 else 'không vượt'} ngưỡng 2% theo errors.json hiện tại",
            "Kết luận v2: Hold — bản nháp; chờ người phụ trách kiểm tra nội dung, bảo mật và quyết định phát hành",
            "Ghi chú: Nhãn giữ nguyên byte; rework giao theo jobs.csv. "
            + f"Hash đã được người chạy xác nhận bằng --hash-reviewed: {', '.join(sorted(reviewed)) or 'không có'}. "
            + f"Guideline sửa theo job: {', '.join(guideline_fixes) or 'không có'}. "
            + f"Split theo đa số của cảnh v1 (hoà thì theo tên split): {', '.join(changed_scenes) or 'không có'}. "
            + f"Báo team panoptic, ảnh ở lại v2: {panoptic_notes}.",
        ]
        (folder / "README.txt").write_text("\n".join(readme) + "\n", encoding="utf-8")
        folder.rename(destination)
    print(f"Đã tạo bản nháp: {destination}")
    print(f"Giữ {len(kept)} ảnh; rework {len(rework)} ảnh; QC v1 {bad}/{len(manifest)} ({rate:.2%}).")
    print("Chưa ghi lineage, chưa đóng gói, chưa xác nhận nhãn đúng hoặc đủ điều kiện phát hành.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True)
    parser.add_argument("--hash-reviewed", nargs="*", default=[], metavar="IMAGE")
    parser.add_argument("--hash-rework", nargs="*", default=[], metavar="IMAGE")
    args = parser.parse_args()
    try:
        build(args)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        parser.exit(1, f"Chưa tạo được v2: {exc}\n")


if __name__ == "__main__":
    main()

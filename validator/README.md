# Validator của nhóm

Giao diện cố định (đề bài):

```
python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]
```

Chỉ đọc thư mục delivery được truyền vào; chỉ thư viện chuẩn; không mạng. Không đọc `_private/`, `data_source/`, annotation COCO; không ghi cứng tên ảnh / id của seed nào. Xem [GUIDE.md](../GUIDE.md) Pha 1–2 và [RULES.md](../RULES.md).

## Ai viết file nào

`validate.py` (TV1) là khung: đọc lô vào đối tượng `Delivery`, gọi từng module, gộp kết quả, ghi file. Mỗi người viết **một file riêng** và commit dưới tên mình; module nào chưa có thì khung chỉ cảnh báo rồi chạy tiếp.

| File | Người | Hàm khung gọi | Loại lỗi |
|---|---|---|---|
| `rules_meta.py` | TV1 | `check(d)` | `missing_image`, `wrong_hash`, `scene_leak`, `guideline_mismatch` |
| `common.py` | TV2 | (hàm dùng chung) | đọc mask panoptic (`scripts/pngutil.py`), đổi box YOLO sang pixel… |
| `rules_label.py` | TV2 | `check(d)` | `invalid_class`, `bbox_out_of_bounds`, `duplicate_box`, `invalid_category_id`, `thing_overlap` |
| `cross_check.py` | TV3 | `candidates(d)`; cung cấp `match(...)` | `class_swap` / `category_swap`, `missing_box` |
| `cross_drift.py` | TV6 | `candidates(d)` (gọi `cross_check.match`) | `bbox_drift`, `instance_merge` |

- `check(d)` trả lỗi luật vào `--out`; `candidates(d)` trả ứng viên vào `--candidates` (cần người xem ảnh mới vào `errors.json`).
- Mỗi phần tử: `{"type": "...", "target": "<tên ảnh không đuôi | scene_id>", "detail": {...}}`. `detail` tuỳ chọn, để người xem ảnh biết vì sao bị cờ (box nào, segment nào, IoU / tỉ lệ pixel…).
- **TV3 chốt chữ ký `match()` trước mốc 0:30** và ghi vào docstring `cross_check.py`, để TV6 làm song song.

## Đối tượng `Delivery` (trong `validate.py`)

| Thuộc tính / hàm | Nội dung |
|---|---|
| `d.root` | thư mục delivery |
| `d.manifest` | `{tên: {image, label, mask, image_sha256, label_sha256, mask_sha256}}` |
| `d.meta` | `{tên: {image, scene_id, split, job_id, guideline_version}}` |
| `d.jobs` | `{job_id: {job_id, annotator, reviewer, guideline}}` |
| `d.classes` | `{0..79: tên lớp}` (ghép với panoptic qua **tên**) |
| `d.panoptic` | nội dung `panoptic.json` (đọc khi cần) |
| `d.names()` | mọi tên ảnh, đã sắp xếp |
| `d.path(rel)` | đường dẫn file trong delivery |
| `d.label_rows(tên)` | `[(số dòng, các cột)]` của file nhãn YOLO, `None` nếu không có file |

## Gộp kết quả

- Mỗi ảnh mang nhiều nhất một lỗi: nếu một ảnh dính nhiều luật, khung giữ theo thứ tự `PRIORITY` trong `validate.py` và in dòng `[gộp]` để nhóm kiểm lại.
- `scene_leak` có target là `scene_id`, không gộp theo ảnh.
- Lỗi gán nhãn chỉ vào `errors.json` cuối qua `scripts/merge_review.py` (lấy dòng `confirmed` trong `review_log.csv`).

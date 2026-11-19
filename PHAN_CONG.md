# Phân công Day 10 Lab — Nhóm 6 người

> Tài liệu nội bộ của nhóm. Tóm tắt bài lab, chia việc cho 6 người, hướng dẫn chi tiết từng phần và lịch theo mốc CHECKPOINTS.
> Thay `TV1…TV6` bằng tên thật, ghi bảng phân công vào `submission/TEAM.md`.

---

## 0. Hiểu bài trong 2 phút

Nhóm nhận **lô v1 gồm 250 ảnh COCO**, mỗi ảnh có nhãn **detection** (YOLO, 80 lớp) và **panoptic** (mask PNG + `panoptic.json`), kèm giấy tờ: `metadata.json` (scene, split, job, guideline), `jobs.csv` (người gán, người kiểm, guideline của job), `changelog.md`, `ticket.md`. Trong lô có lỗi gài theo seed, **không có đáp án để so**.

Nhóm phải làm 6 việc:

| Pha | Việc | Sản phẩm |
|---|---|---|
| P1 | Viết `validator/validate.py` bắt **9 lỗi luật** | `rules.json` |
| P2 | **Đối chiếu** detection ↔ panoptic để sinh ứng viên **5 lỗi gán nhãn**, rồi **mở ảnh xem** từng ứng viên | `candidates.json`, `review_log.csv`, `errors.json` |
| P3 | Tỉ lệ lỗi > 2% thì **HOLD** v1, ghi lineage, hỏi impact `R-021` | `runs/lineage.jsonl` |
| P4 | Đóng gói **lô v2** (không sửa v1): ảnh lỗi detection vào rework, sửa hash/guideline/split | `handover/<id>_v2/` + `.sha256` |
| P5 | Truy vết ticket: `tier_a`, `tier_b`, `notify` | `trace.json` |
| P6 | `security.md` + **đề ẩn 40 phút** (250 ảnh khác, tên mã hoá) | `submission/de_an/` |

**Điểm (100):** đề ẩn 35 · review bằng mắt 15 · bàn giao v2 25 · truy vết 10 · bảo mật 5 · quy trình + vấn đáp 10.

**Ba điều quyết định điểm:**
1. **35 + 15 điểm nằm ở đề ẩn.** Validator và công cụ xem ảnh phải chạy được trên một thư mục `delivery/` bất kỳ, **xong trước khi nhận đề**. Đề ẩn có ảnh lật, nén lại, mức lỗi khác: không được dựa vào tham số trong `inject_release.py`.
2. **F1 phạt báo thừa.** Không tự nhận hết ứng viên. Lỗi gán nhãn nào trong `errors.json` cũng phải có dòng `confirmed` (ghi chú ≥ 20 ký tự, nói **thấy gì** trong ảnh), không thì bị loại trước khi chấm.
3. **Vấn đáp ngẫu nhiên từng người** (3 phút): giải thích một đoạn validator, một dòng review, một con số trong `README.txt`. Ai cũng phải hiểu cả bài, không chỉ phần mình.

**Cấm (bị 0 điểm phần liên quan):** validator đọc `_private/`, `data_source/`, annotation COCO, dùng mạng; sửa `scripts/`; sửa `delivery/`; chạy `--dev-truth` / `--truth-dir`; dò đáp án bằng `score_findings.py`; bịa số; dùng AI thay việc xem ảnh.

---

## 1. Bảng phân công

Khi có 6 người, phần **đối chiếu** (khó nhất và ảnh hưởng nhiều nhất tới điểm đề ẩn) được chia cho **hai người** (TV3 và TV6). Nhờ đó TV4 bớt việc đo nhiễu và có thời gian làm truy vết.

| | Vai trò | Pha chính | File phụ trách |
|---|---|---|---|
| **TV1** | Trưởng nhóm · khung validator · luật **file + metadata** · tích hợp & nộp bài | P0, P1, P6b | `validator/validate.py`, `validator/rules_file.py`, `TEAM.md`, `prompts.md`, `REPORT.md` §1–2 |
| **TV2** | Luật **nhãn detection + panoptic** · tiện ích đọc mask · thử độ bền | P1 | `validator/common.py`, `validator/rules_label.py` |
| **TV3** | Đối chiếu (1): **ghép box ↔ segment** · `class_swap` / `category_swap` · `missing_box` | P2 | `validator/cross_check.py` |
| **TV6** | Đối chiếu (2): **`bbox_drift` · `instance_merge`** · đo nhiễu lô sạch · chọn ngưỡng | P2 | `validator/cross_drift.py`, `REPORT.md` §1 (phần ứng viên/ngưỡng) |
| **TV4** | **Công cụ xem ảnh** · điều phối review · **truy vết** | P2, P5 | `tools/view.py`, `tools/trace_query.py`, `review_log.csv`, `trace.json`, `REPORT.md` §5 |
| **TV5** | **Quyết định + lineage · bàn giao v2 · bảo mật** | P3, P4, P6a | `tools/build_v2.py`, `security.md`, `REPORT.md` §3–4 |

**Việc chung của cả 6 người**
- **Ai cũng xem ảnh ở P2** (RULES bắt buộc). Mỗi dòng `review_log.csv` ghi tên người xem ở đầu ghi chú, ví dụ `[Lan] xe tải mui kín, detection ghi car; panoptic ghi truck đúng`.
- Mỗi người **≥ 2 commit có nội dung**, bằng tên và email của chính mình (`git config user.name` / `user.email` trên máy mình).
- Ai dùng AI thì tự ghi một dòng vào `submission/prompts.md`: prompt, AI sai ở đâu, kiểm lại bằng cách nào.
- Tách file theo bảng trên để **không sửa chung một file**, tránh conflict khi merge.

---

## 2. Cấu trúc code đề xuất

```text
validator/
├── validate.py         # TV1: CLI, đọc delivery, gọi các module, ghi errors.json / candidates.json
├── common.py           # TV2: load_delivery(), yolo_to_px(), đọc mask -> {segment_id: (count, bbox, pixels)}
├── rules_file.py       # TV1: missing_image, wrong_hash, scene_leak, guideline_mismatch
├── rules_label.py      # TV2: invalid_class, bbox_out_of_bounds, duplicate_box, invalid_category_id, thing_overlap
├── cross_check.py       # TV3: match() + class_swap/category_swap, missing_box
└── cross_drift.py  # TV6: bbox_drift, instance_merge (dùng kết quả match() của TV3)
tools/                  # được dùng Pillow, KHÔNG được import từ validator
├── view.py             # TV4: vẽ box + viền segment, phóng to ứng viên
├── trace_query.py      # TV4: sinh trace.json
└── build_v2.py         # TV5: dựng handover/<id>_v2 tự động
```

Validator chỉ dùng thư viện chuẩn. Trong `validate.py` thêm `sys.path` tới thư mục `validator/` và `scripts/` để import `common`, `pngutil`.

> **Giao diện chính thức là [validator/README.md](validator/README.md) do TV1 chốt:** khung gọi `check(d)` (luật) và `candidates(d)` (ứng viên), `d` là đối tượng `Delivery`. Module nào muốn dùng hàm của `common.py` thì gọi `common.load_delivery(d.root)`. Phần dưới là ý tưởng ban đầu, chỗ nào khác README thì theo README.

**Hợp đồng dữ liệu giữa các module (thống nhất ngay ở P0):**
- Mỗi hàm luật nhận `ctx` (dict đã load: `manifest`, `meta`, `jobs`, `classes`, `panoptic`, `delivery_dir`) và trả `list[{"type", "target"}]`.
- `cross_check.match(ctx, image)` (TV3) trả cấu trúc ghép của một ảnh: danh sách box (pixel, tên lớp), danh sách segment thing (không crowd), và ma trận `inside[box][seg]` = tỉ lệ pixel segment nằm trong box. **TV3 chốt chữ ký hàm này trước 0:30** để TV6 code song song (trong lúc chờ, TV6 dùng bản giả lập trả dữ liệu cứng).
- `cross_check.run(ctx)` và `cross_drift.run(ctx)` đều trả `list[{"image", "type", "score", "detail"}]` (`detail` là chữ mô tả, ví dụ `"box#3 car ↔ seg 5 truck, 0.96 pixel trong box"`).
- `validate.py --out X` **chỉ ghi lỗi luật** vào X; `--candidates Y` ghi ứng viên của cả hai module vào Y (mỗi ảnh giữ một ứng viên có `score` cao nhất). Lỗi gán nhãn chỉ vào `errors.json` qua `merge_review.py`.

---

## 3. Lịch làm việc theo mốc

| Giờ | Mốc | TV1 | TV2 | TV3 | TV6 | TV4 | TV5 |
|---|---|---|---|---|---|---|---|
| 0:00–0:15 | CP0 | tải dữ liệu, tạo seed, khung `validate.py` | `common.py` | đọc `panoptic.json`, thử đọc mask | tạo lô sạch, đọc mask cùng TV3 | cài Pillow, khung `view.py` | đọc P3–P4, khung `build_v2.py` |
| 0:15–0:55 | CP1 | 4 luật file/metadata | 5 luật nhãn | `match()` + class swap | `bbox_drift` (dữ liệu giả lập rồi nối `match()`) | `view.py` chạy được | `build_v2.py` phần copy + manifest |
| 0:55–1:20 | | tích hợp, chấm nhiều seed | sửa FP/FN luật, thử độ bền | `missing_box` | `instance_merge`, đo lô sạch, chọn ngưỡng | chia hàng đợi review | label_summary, truyvet, README |
| 1:20–1:50 | CP2 | **cả nhóm xem ảnh** (TV4 chia hàng đợi) → `merge_review.py` | | | | | |
| 1:50–2:05 | CP3 | | | | | | lineage HOLD + impact |
| 2:05–2:45 | CP4 | REPORT §1–2 | thử validator trên lô "giả đề ẩn" | tinh ngưỡng class/missing | tinh ngưỡng drift/merge, số liệu REPORT | `trace_query.py` | dựng v2, `check_handover` |
| 2:45–3:15 | CP5–6a | tổng duyệt, `prompts.md` | ôn vấn đáp | tổng diễn đề ẩn với TV6 | tổng diễn đề ẩn với TV3 | `trace.json`, REPORT §5 | `security.md`, REPORT §3–4 |
| 3:15–3:55 | CP6b | **đề ẩn 40 phút** (mục 10) | | | | | |

---

## 4. TV1 — Trưởng nhóm · khung validator · luật file + metadata

### P0 (15 phút)
1. Tạo repo nhóm tên `K5-L23-DAY10-NHOM<XX>-Release` (public), mời 5 người còn lại. Kiểm Python 3.10+ (`py --version`).
2. Tải dữ liệu (khoảng 1 GB, **mỗi máy một lần**, nên bắt đầu ngay):
   ```bash
   py scripts/download_public.py
   ```
3. Chọn seed luyện tập: số nhóm × 1000 + 7 (ví dụ nhóm 5 → `5007`). Tạo lô **đúng một lần**:
   ```bash
   py scripts/run_lab.py --seeds 5007
   ```
   Tạo thêm seed thử và lô sạch (**không** chạy lại `run_lab.py`, tránh ghi thêm R-021):
   ```bash
   py scripts/inject_release.py --seed 101 --out runs/r101
   ```
   ```bash
   py scripts/inject_release.py --seed 202 --out runs/r202
   ```
   ```bash
   py scripts/inject_release.py --seed 5 --no-faults --out runs/clean
   ```
   Mỗi thành viên tự chạy các lệnh trên trên máy mình với **cùng seed** (cùng seed ra cùng lô). Chỉ máy của TV5 là nơi giữ `runs/lineage.jsonl` chính thức.
4. Điền `submission/TEAM.md` (tên, MSHV, GitHub, phần chính, seed). Commit `P0: chia viec`.

### P1 — khung `validate.py`
- `argparse`: đối số vị trí `delivery`, `--out` bắt buộc, `--candidates` tuỳ chọn.
- Load: `manifest.json["items"]` (dict theo tên ảnh), `metadata.json["items"]` (list → dict theo `image`), `jobs.csv`, `classes.txt`, `panoptic.json`.
- Gọi `rules_file`, `rules_label`; nếu có `--candidates` thì gọi `cross_check` và `cross_drift`, gộp lại.
- **Mỗi ảnh tối đa một lỗi.** Nếu một ảnh dính nhiều luật, giữ theo thứ tự ưu tiên: `missing_image` → `wrong_hash` → `guideline_mismatch` → `invalid_class` → `bbox_out_of_bounds` → `duplicate_box` → `invalid_category_id` → `thing_overlap`. `scene_leak` tính riêng theo `scene_id`. Ảnh đã có lỗi luật thì bỏ khỏi hàng đợi ứng viên.
- Ghi `{"errors": [...]}` sắp xếp ổn định.
- Không đọc gì ngoài thư mục được truyền vào, không có tên ảnh/seed nào trong code.

### P1 — 4 luật của TV1 (`rules_file.py`)
| Lỗi | Cách bắt | Bẫy |
|---|---|---|
| `missing_image` | `delivery / item["image"]` không tồn tại | bỏ qua các luật khác của ảnh đó |
| `wrong_hash` | `hashlib.sha256(path.read_bytes()).hexdigest() != item["image_sha256"]` | phải đọc **bytes** (`rb`), không kiểm định dạng 64 ký tự |
| `scene_leak` | gom `split` theo `scene_id`; cảnh có > 1 split → `{"type":"scene_leak","target":scene_id}` | target là **scene**, không phải ảnh |
| `guideline_mismatch` | `meta["guideline_version"] != jobs[meta["job_id"]]["guideline"]` | so với **job**, không so với ảnh khác |

### Kiểm
```bash
py validator/validate.py runs/r5007/delivery --out runs/r5007/errors.json
```
```bash
py scripts/score_findings.py --run runs/r5007
```
Lặp lại cho `r101`, `r202`; chạy trên `runs/clean/delivery` phải ra **0 lỗi luật**. Mục tiêu CP1: F1 luật ≈ 1.0 trên mọi seed.

### Sau CP1
- Ghép module của TV2, TV3, TV6 vào `validate.py`; chạy lại trên mọi seed sau mỗi lần ai đó push.
- Viết `REPORT.md` §1 (F1 theo từng seed, tách rule / cross_check / overall; phần ứng viên và ngưỡng lấy từ TV6) và §2 (vì sao báo hết ứng viên làm F1 giảm: dùng số thật, ví dụ "báo hết N ứng viên thì precision còn x, F1 còn y; chỉ nhận dòng confirmed thì F1 = z").
- Gom `prompts.md`. Cuối buổi chạy `export_submission.py`, đổi tiêu đề `README.md` thành `# Day 10 Lab — Nhóm <XX>`, push.
- **Chỉ huy đề ẩn** (mục 10).

---

## 5. TV2 — Luật nhãn detection + panoptic · tiện ích mask · thử độ bền

### `common.py` (làm trong 15 phút đầu, TV3, TV6 và TV4 cần dùng)
- `yolo_to_px(line, W, H)` → `(cls, x1, y1, x2, y2)`. Kích thước ảnh lấy từ `panoptic.json["images"]` (`width`, `height`), **không** mở JPG (ảnh có thể thiếu).
- `read_segments(mask_path)` dùng `pngutil.read_rgb` → với mỗi id (= R + G·256 + B·256²), bỏ id 0: số pixel, bbox pixel (xmin, ymin, xmax, ymax), và danh sách/tập pixel (TV3, TV6 cần). Viết một lần, cache theo ảnh vì đọc PNG thuần Python khá chậm.
- Map lớp: `classes.txt` (0–79 → tên) và `categories` (id COCO → tên, `isthing`). Ghép hai bên **qua tên**.

### 5 luật (`rules_label.py`)
| Lỗi | Cách bắt | Bẫy |
|---|---|---|
| `invalid_class` | `int(float(cls))` ngoài `0..79` | đọc số kiểu float rồi ép int |
| `bbox_out_of_bounds` | `x-w/2 < 0`, `y-h/2 < 0`, `x+w/2 > 1`, `y+h/2 > 1` với sai số rất nhỏ (cỡ 1e-4, hoặc ~0,5 pixel sau khi đổi sang pixel) | box lỗi có thể **chỉ tràn mép một chút**; ngưỡng phải chọn bằng cách chạy lô sạch ra 0 |
| `duplicate_box` | cặp box **cùng lớp, cùng w/h** (lệch ≤ ~1 pixel) và **tâm lệch ≤ ~3 pixel** | COCO có cặp box tự nhiên IoU ~0,66 nhưng khác kích thước: **không** dùng IoU đơn thuần |
| `invalid_category_id` | `category_id` của segment không nằm trong `categories` | |
| `thing_overlap` | đếm pixel thật của từng segment trong mask, so với `area` khai trong `segments_info`; `area` > số pixel thật (vượt sai số nhỏ) → lỗi | bỏ id 0 (nền); đếm theo ảnh của chính segment (`file_name` trong annotation) |

### Kiểm và bàn giao
- Chạy trên `r5007`, `r101`, `r202`, `clean`; bảng ghi số FP/FN từng loại (dùng F1 làm tròn của `score_findings.py`, **không** nộp thử từng phần để dò).
- **Thử độ bền** (việc chính sau CP1): tự tạo lô "giả đề ẩn" với seed lạ (ví dụ `--seed 999`, thử thêm `--opaque` nếu script cho phép). Validator không được crash khi thiếu ảnh, label rỗng, dòng thừa khoảng trắng, tên ảnh dạng `img_0001`. Đo thời gian chạy toàn bộ validator (phải dưới vài phút).
- Ôn vấn đáp toàn bộ phần validator luật.

---

## 6. TV3 — Đối chiếu (1): ghép box ↔ segment · class/category swap · missing_box

### Bước ghép (`cross_check.match`): làm trước, TV6 phụ thuộc vào đây
1. Mỗi ảnh: box detection (pixel, tên lớp) và các segment **thing** (`isthing=1`), **bỏ `iscrowd=1`**.
2. Với mỗi cặp box–segment, tính **tỉ lệ pixel của segment nằm trong box** (`inside = số pixel trong box / tổng pixel segment`) và IoU bbox.
3. Ghép mỗi segment với box có `inside`/IoU cao nhất (ghép tham lam, mỗi box dùng một lần). Trả về cả ma trận `inside` để TV6 dùng.
4. IoU bbox **không đủ** để phát hiện lệch hay gộp; tín hiệu chính là pixel mask.

### Tín hiệu của TV3
| Ứng viên | Dấu hiệu | Gợi ý ngưỡng (phải đo lại) |
|---|---|---|
| `class_swap` / `category_swap` | box và segment trùng vị trí (inside cao, IoU cao) nhưng **khác tên lớp** | IoU > 0,7; ghi cả hai tên lớp vào `detail` để người xem quyết định bên nào sai |
| `missing_box` | segment thing **lớn** không có box cùng lớp nào phủ | diện tích > ~1–2% ảnh, inside với mọi box cùng lớp < ~0,5 |

Với cặp khác lớp: `type` trong candidates ghi tạm `class_swap`; người xem ảnh sẽ đổi thành `category_swap` nếu panoptic là bên sai.

### Kiểm
```bash
py validator/validate.py runs/r5007/delivery --out runs/r5007/rules.json --candidates runs/r5007/candidates.json
```
Đưa số ứng viên của mình trên lô sạch và các seed cho TV6 để tổng hợp ngưỡng. Sau khi nhóm review xong, xem F1 `cross_check_review` bằng `score_findings.py`.

---

## 7. TV6 — Đối chiếu (2): bbox_drift · instance_merge · đo nhiễu và chọn ngưỡng

### Tín hiệu của TV6 (`cross_drift.py`)
Dùng kết quả `cross_check.match()` của TV3. Trong lúc TV3 chưa xong (trước ~0:30), viết code với một hàm giả lập trả dữ liệu cứng cùng định dạng, rồi thay bằng hàm thật.

| Ứng viên | Dấu hiệu | Gợi ý ngưỡng (phải đo lại) |
|---|---|---|
| `bbox_drift` | cặp **cùng lớp** đã ghép nhưng một phần đáng kể pixel segment rơi ra ngoài box (box bị dời hoặc co giãn) | inside < ~0,85 trong khi IoU vẫn > ~0,3 |
| `instance_merge` | **một** segment có pixel nằm đáng kể trong **hai** box cùng lớp, và số box lớp đó > số segment lớp đó | mỗi box chứa ≥ ~20% pixel segment |

Ghi rõ trong `detail` box nào, segment nào, tỉ lệ bao nhiêu, để người xem ảnh biết phải nhìn vào đâu.

### Đo nhiễu và chọn ngưỡng cho cả nhóm (làm cùng TV3)
- Chạy `--candidates` trên `runs/clean/delivery` (lô sạch 50 ảnh): mọi ứng viên ở đây là **lệch tự nhiên** của COCO. Lập bảng: số ứng viên từng loại trên lô sạch và trên `r5007`, `r101`, `r202` với vài mức ngưỡng.
- Mục tiêu: hàng đợi trên seed luyện tập **xem hết được trong ~30 phút với 6 người** (khoảng 30–60 ảnh), không bỏ sót lỗi. Sắp ứng viên theo `score` để khi thiếu giờ xem cái chắc nhất trước.
- **Không** dùng `_private` để chỉnh ngưỡng. Ghi bảng số và lý do chọn ngưỡng vào `REPORT.md` §1 (đây là bằng chứng cho 4 điểm "phân biệt lỗi với lệch tự nhiên").
- Lưu ý đề ẩn có độ lệch box và tỉ lệ lỗi khác: chọn ngưỡng dựa trên **lô sạch** (nhiễu tự nhiên), không bám sát mức lệch gài trong `inject_release.py`.

### Tổng diễn đề ẩn (2:45–3:15, cùng TV3)
Chạy cả chuỗi `validate.py --candidates` → `view.py` trên một lô seed lạ, đo thời gian, sửa chỗ chậm hoặc chỗ crash.

---

## 8. TV4 — Công cụ xem ảnh · điều phối review · truy vết

### P1–P2: `tools/view.py` (được dùng Pillow: `py -m pip install pillow`)
- Đầu vào: thư mục delivery + `candidates.json` (+ tuỳ chọn tên ảnh). Đầu ra: `review_png/<ảnh>_<type>.png`.
- Vẽ **box detection** (màu theo lớp, ghi tên lớp) và **viền segment panoptic** (ghi tên category); đánh dấu đậm cặp box/segment trong `detail` của ứng viên.
- Ảnh nhỏ (~240×320): **phóng to 2–3 lần** và thêm ảnh cắt vùng quanh vật. Ghép ảnh gốc | ảnh vẽ cạnh nhau để nhìn vật thật không bị che bởi nét vẽ.
- Phải chạy được với tên ảnh mã hoá (`img_0001`) của đề ẩn và với ảnh bị thiếu.

### P2: điều phối review
1. Lấy hàng đợi từ `candidates.json`, chia đều cho 6 người (bảng tính hoặc file `queue_<tên>.txt`).
2. Mỗi người mở ảnh, ghi vào `runs/r5007/review_log.csv` (`image,type,verdict,note`):
   - `confirmed`: ghi **thấy gì**, ví dụ `[Minh] con vật bên trái là ngựa, detection ghi cow; panoptic ghi horse đúng → class_swap`.
   - `rejected`: ghi **lý do lệch tự nhiên**, ví dụ `[Hà] người bị che 60% sau bàn, box chỉ phủ phần nhìn thấy; nhãn hợp lý`.
   - Khác lớp: **mở ảnh xem nguồn nào đúng**. Detection sai → `class_swap`; panoptic sai → `category_swap`.
   - Ghi chú ≥ 20 ký tự, không chép giống nhau (H3 kiểm ≥ 70% ghi chú khác nhau). AI **không** được thay người xem.
   - Gặp ảnh có **mặt người nhìn rõ** thì báo tên ảnh cho TV5 (dùng cho `security.md`).
3. Gộp:
   ```bash
   py scripts/merge_review.py --rules runs/r5007/rules.json --review runs/r5007/review_log.csv --out runs/r5007/errors.json
   ```
   ```bash
   py scripts/score_findings.py --run runs/r5007
   ```
4. Đảm bảo có **ít nhất vài dòng `rejected`** có lý do (4 điểm rubric). Nếu hàng đợi không có ca lệch tự nhiên, REPORT phải nêu số đo trên lô sạch (TV6 cung cấp).

### P5: `tools/trace_query.py` → `trace.json`
Đọc `incoming/ticket.md` (lấy **lớp** trong dấu `` ` `` và các **scene** được nêu) và `guideline/changelog.md` (lớp đổi quy tắc ở v1.3, guideline cũ là v1.2).
- `tier_a`: ảnh thuộc các scene trong ticket, **job** có guideline cũ (theo `jobs.csv`, **không** theo `guideline_version` của ảnh vì đó có thể là lỗi `guideline_mismatch`), có **≥ 1 box detection** lớp đó trong `labels/` của lô.
- `tier_b`: ảnh cùng điều kiện nhưng ở scene khác (chưa ai báo).
- `notify`: `annotator` + `reviewer` của mọi job chứa ảnh tầng a và b (không báo hết mọi job cũ: bị trừ điểm).
- Đặt tên tham số `--delivery` để chạy được cho cả seed luyện tập và đề ẩn:
  ```bash
  py tools/trace_query.py --delivery runs/r5007/delivery --out runs/r5007/trace.json
  ```
- Viết `REPORT.md` §5: tiêu chí tầng a/b, vì sao lấy guideline theo job.

---

## 9. TV5 — Quyết định + lineage · bàn giao v2 · bảo mật

### P3 (sau khi `errors.json` chốt)
- Tỉ lệ lỗi = **số target khác nhau** trong `errors.json` / 250 (mỗi `scene_leak` tính một). > 2% → **HOLD**.
- `release_id` v1 lấy ở `runs/r5007/delivery/release.json`.
  ```bash
  py scripts/lineage.py record --event decision --release-id <release_id> --decision HOLD
  ```
  ```bash
  py scripts/lineage.py impact --release-id <release_id>
  ```
  Kết quả mong đợi: `R-021: affected=True action=review_or_retrain`. **Ghi mỗi sự kiện đúng một lần**, trên máy giữ `runs/lineage.jsonl`.

### P4: `tools/build_v2.py` (viết sẵn từ đầu buổi, chạy lại được mỗi khi `errors.json` đổi)
Tạo `runs/r5007/handover/<release_id>_v2/`, **không sửa gì trong `delivery/`**:

| Lỗi | Xử lý |
|---|---|
| `missing_image`, `invalid_class`, `bbox_out_of_bounds`, `duplicate_box`, `class_swap`, `bbox_drift`, `missing_box` | đưa vào `rework_queue.csv`, **bỏ khỏi v2** (cả ảnh lẫn nhãn) |
| `wrong_hash` | **mở ảnh kiểm**: nguyên vẹn → giữ trong v2, `manifest.csv` ghi hash thật; hỏng → rework |
| `guideline_mismatch` | giữ ảnh; `truyvet.csv` ghi guideline **theo job** |
| `scene_leak` | giữ ảnh; đưa **cả cảnh** về một split (split của đa số ảnh trong cảnh) trong `truyvet.csv` |
| `invalid_category_id`, `thing_overlap`, `category_swap`, `instance_merge` | **ở lại v2** (nhãn detection vẫn đúng); liệt kê ở mục Ghi chú của `README.txt` để báo team panoptic |

Các phần của v2:
- `images/`, `labels/`: copy **nguyên byte** từ v1 (dùng `shutil.copyfile`), tên ảnh và nhãn phải khớp nhau.
- `rework_queue.csv`: `image,type,annotator,reviewer,action`, người lấy theo `jobs.csv` của job chứa ảnh; `action` ví dụ `gan_lai`.
- `manifest.csv`: `file,sha256` cho **mọi** file trong `images/` và `labels/`, đường dẫn dạng `images/x.jpg`.
- `label_summary.csv`: `class,count` theo tên trong `classes.txt`, dòng cuối `TOTAL`.
- `truyvet.csv`: `image,scene_id,split,job_id,annotator,reviewer,guideline` cho mọi ảnh trong v2.
- `README.txt` theo `templates/README.txt`; các khoá phải đúng chữ: `Release:`, `Parent:`, `Số ảnh:`, `Số nhãn:`, `Guideline:`, `QC v1: <n>/250 = x,x%`, `Kết luận v1: Hold — ...`, `Kết luận v2: Release — ...`, `Ghi chú: ...`. Số liệu **sinh từ file thật**, không gõ tay.

Rồi:
```bash
py scripts/pack_release.py runs/r5007/handover/<release_id>_v2
```
```bash
py scripts/lineage.py record --event release --release-id <release_id>_v2 --parent <release_id>
```
```bash
py scripts/check_handover.py --run runs/r5007
```
Sửa hết FAIL (bảng "Lỗi hay gặp" cuối GUIDE). Đổi bất kỳ file nào trong v2 thì chạy lại `pack_release.py`. Nếu lỡ sửa `delivery/` (H1 FAIL): xoá `runs/r5007`, tạo lại bằng `inject_release.py --seed 5007 --out runs/r5007` (không chạy lại `run_lab.py`).

### P6a: `runs/r5007/security.md` (theo `templates/security.md`, không chép slide)
- **Ca USB:** không chép ra USB, không gửi email cá nhân, không nhờ người khác làm hộ; làm tiếp trên máy/VPN công ty hoặc báo trưởng nhóm xin thêm giờ.
- **Năm việc:** mở job được giao trên máy công ty (được); chụp màn hình gửi người quen, chép lô ra USB, dán nhãn thật lên chatbot, đưa tài khoản CVAT cho đồng nghiệp (không). Mỗi việc một lý do.
- **Ca khuôn mặt:** kết luận **Hold + báo người phụ trách**; không tự làm mờ/xoá (làm đổi dữ liệu ngoài quy trình, mất truy vết, có thể ảnh hưởng nhãn). **Nêu tên ít nhất một ảnh thật trong lô** có mặt người nhìn rõ (cả nhóm báo cho TV5 khi gặp lúc review). Tiêu đề mục phải chứa chữ "khuôn mặt", không còn `<<...>>`.

### REPORT §3–4
- §3: QC v1 a/250, kết luận, vì sao R-021 phải xem lại hoặc train lại (model đã học từ nhãn sai, đổi dataset không sửa được trọng số).
- §4: hash chứng minh file **không bị đổi** từ lúc lập manifest; **không** chứng minh nhãn đúng, ảnh đúng nội dung hay người gán làm đúng guideline.

---

## 10. Kịch bản đề ẩn (40 phút, CP6b)

**Chuẩn bị trước (trước 3:15):** TV3 và TV6 chạy thử toàn bộ chuỗi dưới đây trên một lô seed lạ, đo thời gian. Mọi người đã có Pillow và `view.py` chạy được.

| Phút | Việc | Ai |
|---|---|---|
| 0–3 | Tải `de_an.zip` ở tab Releases của repo đề, giải nén vào gốc repo → `delivery/` | TV1 |
| 3–6 | `py validator/validate.py delivery --out submission/de_an/rules.json --candidates submission/de_an/candidates.json` | TV1 |
| 3–8 | `py tools/view.py ...` sinh ảnh ứng viên, chia hàng đợi 6 phần | TV4 |
| 3–10 | `py tools/trace_query.py --delivery delivery --out submission/de_an/trace.json`, kiểm tay với ticket | TV4 → TV5 kiểm |
| 6–10 | Xem nhanh số ứng viên: quá nhiều so với lúc luyện tập thì sắp theo `score`, ưu tiên xem cái chắc trước | TV6 + TV3 |
| 8–28 | **Cả 6 người xem ảnh**, ghi `submission/de_an/review_log.csv` (ghi chú cụ thể, có tên người xem) | cả nhóm |
| 28–32 | `py scripts/merge_review.py --rules submission/de_an/rules.json --review submission/de_an/review_log.csv --out submission/de_an/errors.json` | TV1 |
| 32–36 | Kiểm: mọi lỗi gán nhãn có dòng `confirmed`; JSON hợp lệ; không có thư mục `delivery/` trong commit | TV2 + TV6 |
| 36–40 | Commit + push | TV1 |

Lưu ý: xoá `submission/de_an/rules.json` trước khi nộp nếu không muốn để lại (không bắt buộc). **Không commit `delivery/`**.

---

## 11. Trước khi nộp (TV1 duyệt)

```bash
py scripts/check_handover.py --run runs/r5007
```
```bash
py scripts/export_submission.py --run runs/r5007
```
- [ ] Validator chạy trên `runs/clean` không báo lỗi luật nào.
- [ ] `check_handover.py` không còn FAIL.
- [ ] `submission/lineage.jsonl` có HOLD v1 và release v2 có parent.
- [ ] `TEAM.md` (đủ 6 người), `REPORT.md` (6 mục, số thật), `prompts.md` đã điền.
- [ ] `submission/de_an/` có `errors.json`, `candidates.json`, `review_log.csv`, `trace.json`.
- [ ] Tiêu đề `README.md` là `# Day 10 Lab — Nhóm <XX>`.
- [ ] Mỗi người (cả 6) ≥ 2 commit có nội dung bằng tài khoản của mình.
- [ ] Không commit `data_source/`, `runs/`, `*.zip`, `delivery/`.

## 12. Ôn vấn đáp (mỗi người tự trả lời được)

- `wrong_hash` vì sao phải tính lại sha256? `scene_leak` target là gì? Vì sao `guideline_mismatch` so với job?
- Lô sạch vẫn có ứng viên vì sao? Báo hết ứng viên thì precision/F1 đổi thế nào (nêu số của nhóm)?
- Detection ghi `car`, panoptic ghi `truck`: làm sao biết bên nào sai?
- Vì sao IoU bbox không đủ để bắt `bbox_drift` và `instance_merge`, mà phải dùng pixel mask?
- Đổi dataset có sửa được model đã train không? Vì sao ngưỡng tính theo tỉ lệ ảnh lỗi?
- Lỗi nào sửa trong v2, lỗi nào gán lại, lỗi nào ở lại? Hash chứng minh gì, không chứng minh gì? Vì sao không ghi đè v1?
- Tầng a khác tầng b thế nào? Vì sao lấy guideline theo job?
- Thấy khuôn mặt rõ: vì sao Hold + báo người phụ trách mà không tự làm mờ?
- Giải thích được một con số trong `README.txt` v2 (Số ảnh, Số nhãn, QC v1).

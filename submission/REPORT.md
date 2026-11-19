# Báo cáo nhóm 36

## 1. Số liệu luyện tập
**Kết luận trước:** trên seed luyện tập 36, bài nộp có **20 lỗi / 250 ảnh** (12 lỗi luật + 8 lỗi gán nhãn đã xem ảnh và xác nhận). Tự đo bằng `score_findings.py` (in làm tròn một chữ số, chạy **một lần** trên danh sách cuối, không dùng để dò) cho F1 ≈ 1,0 ở cả ba nhóm. Lô sạch không sinh lỗi luật hay ứng viên nào.

- F1 theo seed (rule / cross_check / overall):
  - **seed 36** (bản nộp `submission/r36/errors.json`): **1,0 / 1,0 / 1,0**; truy vết tier_a / tier_b / notify: 1,0 / 1,0 / 1,0.
  - **seed 1036** (lô thử, tạo bằng `inject_release.py`, chưa xem ảnh nên chỉ nộp lỗi luật): **1,0 / — / 0,7**. Overall thấp vì phần lỗi gán nhãn chưa nộp, không phải vì luật sai.
  - Lỗi luật đi từ 0,5 (seed 36) / 0,7 (seed 1036) khi mới có 4 luật của TV1 lên ≈ 1,0 trên cả hai seed sau khi ghép 5 luật của TV2.
- Số ứng viên trên lô sạch (`--no-faults`, seed 5, 50 ảnh pool calib): **0** ứng viên và **0** lỗi luật. Hàng đợi trên seed luyện tập 36: **14 ứng viên trên 11 ảnh** (5 `missing_box`, 4 swap, 4 `bbox_drift`, 1 `instance_merge`), ghi thành 12 dòng `review_log.csv` (8 `confirmed`, 4 `rejected`); seed 1036: 6 ứng viên / 6 ảnh. Validator chạy 18,7 giây cho 250 ảnh và 4,6 giây cho 50 ảnh (Windows, Python 3.14), đủ nhanh cho đề ẩn 40 phút.
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): mọi ngưỡng chọn bằng số đo trên **lô sạch** (lệch tự nhiên của COCO), rồi kiểm số ứng viên trên seed 36 và 1036.
  - **4 luật file + metadata (TV1)** không cần ngưỡng: so đúng sha256 tính lại trên bytes, tập split của mỗi cảnh, guideline của ảnh so với guideline của **job**.
  - **5 luật nhãn (TV2)**, đo bằng `validator/calib_tv2.py` trên lô sạch: tràn mép tự nhiên lớn nhất 0,000001 (435 box) nên `OOB_EPS = 1e-4`; trong 1.239 cặp box cùng lớp, cặp tự nhiên giống nhau nhất vẫn chênh kích thước ≥ 2,3 px, còn box bị chép chênh 0 px nên `DUP_SIZE_PX = 1`, `DUP_CENTER_PX = 3` (không dùng IoU vì COCO có cặp box thật chồng tới IoU ~0,66); `area` khớp số pixel thật ở 643/643 segment nên `OVERLAP_TOL = 0`.
  - **Đối chiếu phần 1 (TV3)**: `pair_cover 0,70`, `pair_fill 0,10`, `missing_area 0,01`, `missing_cover 0,50`. Quét lưới trên lô sạch (pair_cover 0,5–0,7, pair_fill 0,1–0,25, missing_area 0,002–0,03, missing_cover 0,3–0,7) đều ra 0 ứng viên, nên hạ `pair_fill` từ 0,25 xuống 0,10 để không mất ca vật xoè (chim/diều) mà không thêm báo thừa.
  - **Đối chiếu phần 2 (TV6)**: `drift_bbox_iou_upper 0,78`, `drift_min_center_dist 0,10`, các ngưỡng `merge_*`, đo bằng `validator/calib_tv6.py` trên lô sạch (0 ứng viên). Rủi ro đã biết: chú thích của `merge_min_seg_pixels = 900` dựa vào mức gài lỗi của đề; đề ẩn đổi mức lỗi nên ngưỡng này có thể bỏ sót.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
F1 tính trên cặp (`type`, `target`), nên **mỗi cặp báo thừa bị trừ như một cặp bỏ sót**. Ứng viên chỉ là "nguồn detection và panoptic bất đồng", không phải lỗi; chính ảnh mới cho biết có lỗi hay không và bên nào sai.

Với số của nhóm ở seed 36: 14 ứng viên gộp thành 12 cặp (`type`, `target`). Xem ảnh, nhóm **bác 4 cặp** vì là lệch tự nhiên hoặc hệ quả của lỗi khác trên cùng ảnh: `000000007386` `bbox_drift` (hai box ôm đúng hai xe đạp, độ phủ thấp vì panoptic gộp hai xe, lỗi thật là `instance_merge`), `000000014007` `bbox_drift` (box ôm đúng con mèo, mask hỏng do `thing_overlap`), `000000004495` và `000000020059` `missing_box` (box có ở file nhãn nhưng mang mã lớp 80, lỗi thật là `invalid_class`). Mỗi ảnh mang nhiều nhất một lỗi, nên cả 4 cặp này chắc chắn là FP. Ngoài ra 4 ứng viên swap đều ra cùng một loại; xem ảnh mới tách được 2 `class_swap` (detection sai) và 2 `category_swap` (panoptic sai).

Ước tính nếu nộp hết ứng viên mà không xem ảnh (giả sử bản nộp của nhóm là đúng, như F1 ≈ 1,0 cho thấy): 12 lỗi luật + 12 cặp ứng viên, trong đó 4 cặp bị bác là FP và 2 swap sai loại vừa là FP vừa làm thiếu 2 `category_swap`. TP = 18, FP = 6, FN = 2: precision = 18/24 = 0,75, recall = 18/20 = 0,90, **F1 ≈ 0,82**, so với ≈ 1,0 khi chỉ nộp lỗi luật cộng các dòng `confirmed`. Recall gần như không tăng (ứng viên đúng thì xem ảnh cũng giữ lại), còn precision giảm theo đúng số ứng viên sai. Lô sạch ra 0 ứng viên nên ở lô luyện tập không có thêm nhiễu tự nhiên; đề ẩn dùng ảnh khác, đã lật và nén lại, nên số ứng viên lệch tự nhiên có thể nhiều hơn và việc báo hết còn bị trừ nặng hơn.

## 3. Quyết định và lineage

Seed 36, v1 `lab250_3c9a0e0e4b9c`: errors.json hiện có 20 target lỗi / 250 ảnh = 8%, vượt ngưỡng 2% nên kết luận Hold. Mỗi scene_leak được tính một đơn vị theo quy ước bài.

Lineage đã ghi decision HOLD cho v1 và event release cho `lab250_3c9a0e0e4b9c_v2` với parent v1. Lệnh impact in `R-021: affected=True action=review_or_retrain`. Thay dataset không tự sửa trọng số model đã học; R-021 cần đánh giá lại hoặc train lại. Sự kiện release ghi nhận phiên bản v2 trong lineage; README v2 hiện vẫn Hold chờ kiểm tra bảo mật và quyết định phát hành.

Bản v2 có 240 ảnh, 1.681 nhãn; 10 ảnh đưa vào rework, giao đúng annotator/reviewer theo job. Ảnh chỉ lỗi panoptic được giữ lại và ghi chú cho team panoptic. Guideline theo job, cảnh rò split được gom theo split đa số. Phạm Trần Anh trực tiếp xác nhận ảnh wrong_hash `000000001993` mở bình thường và không thấy bất thường; giữ ảnh, ghi hash thực tế trong manifest v2. V1 và nhãn giữ lại không bị sửa.

Bộ kiểm gốc chạy trên máy TV5: H1–H17 PASS, 0 FAIL. security.md dùng ảnh 000000020992.jpg làm minh họa ca khuôn mặt và giữ kết luận Hold + báo người phụ trách. Kết quả này xác nhận định dạng và tính nhất quán, không chứng minh nhãn đúng hoặc thay thế phê duyệt phát hành. TV5 cần kiểm lại ảnh minh họa trước khi nộp; nhóm cần xác nhận errors.json là bản cuối và thống nhất máy giữ lineage cuối. Chạy lại kiểm tra khi đầu vào thay đổi.

## 4. Hash chứng minh gì, không chứng minh gì?

SHA-256 được tính trên byte thực tế của file. Khi tính lại và đối chiếu với một mã băm tham chiếu đáng tin cậy, hash giúp phát hiện nội dung file có thay đổi hay không, chẳng hạn trong quá trình sao chép hoặc bàn giao. Trong bài này, manifest.csv ghi hash của từng ảnh và nhãn thuộc v2; file .sha256 bên cạnh thư mục v2 ghi hash của gói ZIP được tạo bằng pack_release.py. Hai loại hash có phạm vi đối chiếu khác nhau.

Hash khớp không chứng minh nhãn đúng: một ảnh gán nhầm lớp hoặc box lệch vẫn có hash hợp lệ. Hash cũng không chứng minh dữ liệu đã theo đúng guideline, không rò rỉ train/val, đã xử lý yêu cầu riêng tư hoặc được phép phát hành. Những điều này cần validator, đối chiếu nguồn, review bằng mắt và kiểm tra quy trình. Nếu cả file lẫn mã băm tham chiếu cùng bị thay đổi, việc chúng khớp nhau cũng không đủ chứng minh nguồn gốc hay tính xác thực; hash không thay thế chữ ký số hoặc kiểm soát quyền truy cập.

Với wrong_hash, người trong nhóm phải mở ảnh kiểm tra trước. Nếu ảnh đúng nội dung và còn nguyên, nhóm giữ nguyên ảnh trong v2 và ghi hash tính lại; nếu ảnh hỏng hoặc sai nội dung thì đưa vào rework. Nhóm không chỉnh delivery v1 để làm cho hash khớp. Sau khi thay đổi nội dung v2, cần tính lại manifest cho các file liên quan và đóng gói lại để mã .sha256 khớp bản cuối.

## 5. Truy vết

**Đầu vào (seed 36).** `incoming/ticket.md`: team AI báo model hay bỏ sót `bottle` bị che hoặc ở mép ảnh, thấy rõ ở `scene_742` và `scene_768`. `guideline/changelog.md`: từ **v1.3**, `bottle` bị che trên 50 % hoặc cắt ở mép **vẫn phải gán box** (v1.2 cho bỏ qua); lớp khác không đổi. Như vậy guideline cũ là v1.2, gồm các job **J01–J04** trong `jobs.csv`; J05–J10 theo v1.3.

**Tiêu chí** (`tools/trace_query.py`, chỉ đọc `delivery/`):

- Một ảnh *bị ảnh hưởng* khi: (1) job của ảnh theo guideline cũ, tra `metadata.json` → `job_id` → cột `guideline` của `jobs.csv`; và (2) ảnh có ít nhất một **box detection** lớp `bottle` (class_id 39) trong `labels/<ảnh>.txt`. Không dùng panoptic, vì lô v2 là sản phẩm detection và lỗi nằm ở box.
- **tier_a** = ảnh bị ảnh hưởng nằm trong cảnh team AI nêu (`scene_742`, `scene_768`).
- **tier_b** = các ảnh bị ảnh hưởng ở cảnh khác, chưa ai báo.
- **notify** = `annotator` và `reviewer` của mọi job chứa ảnh tier_a hoặc tier_b.

**Kết quả** (`runs/r36/trace.json`):

| Tầng | Ảnh | Ghi chú |
| --- | --- | --- |
| tier_a (2) | `000000005193` (scene_742, J03, 1 box bottle), `000000007574` (scene_768, J04, 2 box) | 8 ảnh còn lại của hai cảnh không có box bottle |
| tier_b (4) | `000000002685` (J02, 8 box), `000000006471` (J03, 2), `000000008021` (J04, 3), `000000009590` (J04, 1) | |
| notify (6) | A02, A03, A05, Q01, Q02, Q03 | người gán và người kiểm của J02, J03, J04; J01 không có ảnh nào có box bottle |

Cả lô có 18 ảnh có box `bottle`. 12 ảnh thuộc job v1.3 bị loại đúng, vì người gán đã làm theo quy tắc mới.

**Vì sao lấy guideline theo job, không theo ảnh.** Phiên bản guideline được chốt khi **giao job**: người gán làm cả job theo một bản, nên job mới cho biết ảnh thật sự được gán theo quy tắc nào. Trường `guideline_version` ghi ở từng ảnh có thể sai, và sai lệch đó chính là lỗi `guideline_mismatch` mà validator bắt. Ở seed 36 có 2 ảnh như vậy: `000000000885` (job J01 = v1.2, ảnh ghi v1.3) và `000000015335` (job J06 = v1.3, ảnh ghi v1.2). Nếu lọc theo trường của ảnh, một ảnh như `000000000885` mà có box `bottle` sẽ bị loại khỏi danh sách dù thực tế được gán theo v1.2; ngược lại một ảnh như `000000015335` sẽ bị kéo vào nhầm. Ở seed này cả hai ảnh đều không có box `bottle` nên kết quả không đổi, nhưng tiêu chí theo job là cách duy nhất không phụ thuộc vào một trường có thể đã sai.

**Kiểm lại.** Đối chiếu tay 10 ảnh của `scene_742` và `scene_768` (job, guideline của job, số box `bottle`). `score_findings.py` (tự đo) cho tier_a, tier_b, notify ≈ 1,0 trên seed 36 và trên 3 seed thử (11, 22, 4007; lớp đổi lần lượt là `wine glass`, `truck`, `wine glass`), cho thấy script không bị gắn cứng vào seed 36. `check_handover.py` H16 yêu cầu tier_a và notify không rỗng, và mã người phải có trong `jobs.csv`: đạt.

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)

1. **`release_id` phụ thuộc máy, cùng seed không cho cùng lô.** `scripts/inject_release.py` ghi `manifest.json`, `metadata.json`, `release.json`, `classes.txt`… bằng `write_text()`, nên trên Windows mọi dòng thành CRLF; mask PNG nén bằng zlib của bản Python đang chạy nên cũng khác byte giữa các máy. Vì `release_id` = sha256 của `manifest.json` + `metadata.json`, cùng seed 36 cho: Windows / Python 3.14 → `lab250_3c9a0e0e4b9c`; Linux (WSL) / Python 3.10 → `lab250_463d4f677187`; máy Mac của TV5 ra một mã khác nữa. Ảnh JPG và nhãn YOLO vẫn giống từng byte; khác là `manifest.json` và 250 mask PNG (mask khác byte nhưng cùng nội dung pixel), 5 file text chỉ khác CRLF/LF. Hệ quả: `export_submission.py --import` tạo lại lô trên máy người chấm có thể ra mã khác với lineage và tên thư mục `handover/<release_id>_v2` của nhóm. Nhóm xử lý bằng cách cả nhóm dùng **chung một `delivery/` gốc** (gói từ máy TV1, kiểm lại ra đúng `lab250_3c9a0e0e4b9c`) thay vì tự tạo lại trên từng máy. Đề xuất: ghi file với `newline="\n"` và tính `release_id` trên nội dung đã chuẩn hoá (hoặc trên hash pixel của mask).
2. **`pack_release.py` không cho cùng mã `.sha256` trên mọi máy (H15).** Script nén ZIP bằng `ZIP_DEFLATED`; byte nén phụ thuộc thư viện zlib. Cùng thư mục v2 của nhóm: `check_handover.py` bản gốc chạy bằng Python 3.10 / zlib 1.2.11 (WSL) đạt **17 PASS, 0 FAIL**; chạy bằng Python 3.14 trên Windows (zlib-ng 1.3.1) thì **H15 FAIL** dù nội dung không đổi. Docstring "cùng nội dung thì cùng mã băm, trên mọi máy" chưa đúng. Đề xuất: dùng `ZIP_STORED` hoặc chấm H15 bằng hash của từng file trong manifest. Người chấm nên chạy `check_handover.py` bằng Python dùng zlib chuẩn (như máy TV5 đã đóng gói).
3. **`run_lab.py` trên Windows dừng giữa chừng nếu không đặt `PYTHONUTF8=1`.** Tiến trình con `inject_release.py` in tiếng Việt ra console cp1252 và chết vì `UnicodeEncodeError` sau khi đã ghi một phần `delivery/` nhưng **chưa** ghi lineage. Nhóm đặt `PYTHONUTF8=1` rồi chạy lại và kiểm `runs/lineage.jsonl` chỉ có đúng 2 dòng (`inject`, `train R-021`).

Các điểm trên sẽ được báo cho giảng viên khi nộp bài; nhóm không sửa file nào trong `scripts/`.

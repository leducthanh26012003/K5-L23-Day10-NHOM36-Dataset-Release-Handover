# Báo cáo nhóm 36

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall): <<seed: ... / ... / ...>>
- Số ứng viên trên lô sạch (`--no-faults`): <<...>>; hàng đợi trên seed luyện tập: <<... ảnh>>
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): <<...>>

## 2. Vì sao báo hết ứng viên làm F1 giảm?
<<Trả lời bằng số của nhóm.>>

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
<<>>

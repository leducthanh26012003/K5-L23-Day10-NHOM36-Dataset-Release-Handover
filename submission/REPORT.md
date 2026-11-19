# Báo cáo nhóm 36

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall): <<seed: ... / ... / ...>>
- Số ứng viên trên lô sạch (`--no-faults`): <<...>>; hàng đợi trên seed luyện tập: <<... ảnh>>
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): <<...>>

## 2. Vì sao báo hết ứng viên làm F1 giảm?
<<Trả lời bằng số của nhóm.>>

## 3. Quyết định và lineage
<<QC v1 a/b, kết luận, vì sao R-021 phải xem lại hoặc train lại.>>

## 4. Hash chứng minh gì, không chứng minh gì?
<<>>

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

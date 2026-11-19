# Báo cáo nhóm 36

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall):
  - Seed 36 (luyện tập): rule F1 = 1.0 (12/12 lỗi luật) / cross_check F1 = 1.0 (sau review) / overall F1 = 1.0. (Nếu chỉ nộp lỗi luật mà chưa review gộp vào: rule F1 = 1.0, overall F1 ≈ 0.75).
- Số ứng viên trên lô sạch (`--no-faults`): **0 ứng viên** (độ đặc hiệu 100%, không có báo giả trên 50 ảnh COCO của `runs/clean`).
- Hàng đợi trên seed luyện tập: **14 ứng viên** trên 250 ảnh của `runs/r36` (TV6: 5 ứng viên gồm 4 drift, 1 merge; TV3: 9 ứng viên gồm 5 missing, 4 swap). Trên seed 101: 9 ứng viên; trên seed 202: 11 ứng viên. Kích thước hàng đợi tối ưu giúp đội 6 người xem hết trong ~10-15 phút.
- Ngưỡng đã chọn và cách chọn (**HOÀN TOÀN KHÔNG DÙNG `_private`**, chỉ đo đạc phân phối trên lô sạch `runs/clean`):
  - `bbox_drift`:
    - Đo trên 536 cặp cùng lớp ở lô sạch: trung vị độ lệch tâm (`center_dist`) chỉ là 0.0082, 90% cặp tự nhiên có lệch tâm < 0.10; trung vị IoU đạt 0.9593, 90% cặp có IoU > 0.78; mask cover trung vị = 1.0000.
    - Chọn `drift_min_center_dist = 0.10` (vượt ngưỡng 90% của độ lệch tự nhiên) và `drift_bbox_iou_upper = 0.78` (chỉ kích hoạt khi IoU bị sụt giảm bất thường).
    - Ngưỡng `drift_cover_upper = 0.70` (khi ≥ 30% pixel vật rơi ra ngoài hộp) và `drift_cover_lower = 0.15`.
    - Ngưỡng loại trừ láng giềng `drift_other_cover_threshold = 0.75`: nếu segment đã có một box khác cùng lớp ôm trọn ≥ 75% thì box hiện tại chỉ là che khuất/láng giềng, không báo drift.
  - `instance_merge`:
    - `merge_min_seg_pixels = 900` (đảm bảo vật đủ lớn để phân biệt với nhiễu mask).
    - `merge_box_min_fill = 0.38` và `merge_box_max_cover = 0.85` (loại trừ trường hợp 1 vật đơn lẻ).
    - `merge_max_containment = 0.40` (2 box tách biệt, không lồng nhau) và `merge_sum_cover_min = 0.70` (2 box cùng giải thích phần lớn mask).

## 2. Vì sao báo hết ứng viên làm F1 giảm?
- Danh sách ứng viên (`candidates.json`) sinh ra từ các bất thường hình học đối chiếu giữa Detection và Panoptic, chưa thể khẳng định 100% là lỗi gán nhãn hay là hiện tượng che khuất tự nhiên trong ảnh (ví dụ: vật bị che khuất một phần, hoặc nhiều vật cùng loại đứng sát nhau).
- Trên seed luyện tập 36, hàng đợi có 14 ứng viên nhưng thực tế chỉ có 8 lỗi gán nhãn thật:
  - Nếu nộp thẳng toàn bộ 14 ứng viên vào `errors.json` mà không review mắt: ta vô tình nộp thêm 6 lỗi giả (False Positives). Độ chính xác (Precision) của nhóm lỗi đối chiếu bị kéo tụt xuống chỉ còn ~57%, kéo F1 tổng từ 1.0 tụt xuống còn ~0.82.
  - Trường hợp nghiêm trọng hơn (như khi thuật toán chưa calibrate bị lỗi toạ độ đẩy ra 999 ứng viên): nộp toàn bộ sẽ đưa vào 980+ False Positives, làm Precision sụp đổ xuống dưới 2%, phá huỷ hoàn toàn điểm F1 (F1 tụt về gần 0).
- Vì vậy, quy trình chuẩn bắt buộc phải có bước con người mở ảnh xem (Pha 2): chỉ xác nhận `confirmed` khi mắt thấy rõ nhãn sai sự thật, và đánh dấu `rejected` kèm lý do với các ca lệch tự nhiên. Khi đó, FP = 0 và F1 đạt 1.0 tuyệt đối.

## 3. Quyết định và lineage
<<QC v1 a/b, kết luận, vì sao R-021 phải xem lại hoặc train lại.>>

## 4. Hash chứng minh gì, không chứng minh gì?
<<>>

## 5. Truy vết
<<Tiêu chí tầng a/b, vì sao lấy guideline theo job.>>

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>

# Nhóm 36

- Seed luyện tập: 36 (`python scripts/run_lab.py --seeds 36` → `runs/r36/`)
- Repo: https://github.com/leducthanh26012003/K5-L23-Day10-NHOM36-Dataset-Release-Handover

| Vai | Họ và tên | MSHV | Tài khoản GitHub | Phần chính |
|---|---|---|---|---|
| TV1 | Lê Đức Thanh | 2A202603328 | leducthanh26012003 | Trưởng nhóm: chuẩn bị dữ liệu và seed; khung `validator/validate.py`; 4 luật file + metadata (`rules_meta.py`: `missing_image`, `wrong_hash`, `scene_leak`, `guideline_mismatch`); ghép code; REPORT §1–2; chỉ huy đề ẩn và nộp bài |
| TV2 | Phạm Quang Huy | 2A202604055 | feedfoot | `validator/common.py` đọc lô, nhãn YOLO, mask (có `segment_pixels` cho TV3 và TV6); 5 luật nhãn (`rules_label.py`: `invalid_class`, `bbox_out_of_bounds`, `duplicate_box`, `invalid_category_id`, `thing_overlap`); `calib_tv2.py` đo ngưỡng trên lô sạch; `tests/test_rules_label.py` tự cài lỗi để kiểm; thử validator trên nhiều seed, lô sạch, tên ảnh mã hoá; đo thời gian chạy |
| TV3 | Nguyễn Viết Minh | 2A202604043 | minh23012003 | Đối chiếu phần 1 (`cross_check.py`): hàm `match()` ghép box với mask (chốt chữ ký trước 0:30); ứng viên `class_swap` / `category_swap`, `missing_box` |
| TV6 | <<>> | <<>> | <<>> | Đối chiếu phần 2 (`cross_drift.py`): ứng viên `bbox_drift`, `instance_merge`; đo nhiễu trên lô sạch, chọn ngưỡng; số liệu cho REPORT §1 |
| TV4 | <<>> | <<>> | <<>> | Công cụ xem ảnh `view.py`; chia ảnh cần xem; gộp `review_log.csv`; truy vết `trace.json` (`trace_query.py`); REPORT §5 |
| TV5 | <<>> | <<>> | <<>> | Lineage (HOLD v1, kiểm `R-021`); dựng lô v2 (`build_v2.py`); `check_handover.py` hết FAIL; `security.md`; REPORT §3–4 |

Mọi người đều xem ảnh ở Pha 2 và mỗi người có ít nhất 2 commit có nội dung dưới tên mình.

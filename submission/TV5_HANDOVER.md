# Bàn giao TV5 — Phạm Trần Anh

- MSHV: 2A202604057; GitHub: GemmaP512.
- Seed 36; v1: `lab250_3c9a0e0e4b9c`; v2: `lab250_3c9a0e0e4b9c_v2`.
- Dùng delivery gốc TV1 cung cấp. Bản tạo lại trên Mac đã cho ID khác; cần kiểm tra release ID tính từ manifest và metadata trước khi dùng kết quả.
- V2 có 240 ảnh, 1.681 box, 10 ảnh rework. Lỗi panoptic giữ ảnh detection và ghi chú trong README v2.
- V1 HOLD: 20/250 = 8%. Impact: `R-021: affected=True action=review_or_retrain`.
- Kết luận v2 hiện Hold, không phải phê duyệt đưa dữ liệu vào train.

## Kiểm tra và tái chạy

Chạy từ gốc repo, với đúng delivery gốc và các kết quả trong runs/r36:

```bash
python3 tools/build_v2.py --run runs/r36 --hash-reviewed 000000001993
python3 scripts/pack_release.py runs/r36/handover/lab250_3c9a0e0e4b9c_v2
python3 scripts/check_handover.py --run runs/r36
python3 scripts/export_submission.py --run runs/r36
```

build_v2.py không ghi đè thư mục v2 đã có. Di chuyển bản cũ sang vị trí dự phòng trước khi dựng lại. Chỉ dùng --hash-reviewed sau khi trực tiếp kiểm ảnh; Phạm Trần Anh đã xác nhận ảnh 000000001993 mở bình thường. Sau khi dựng lại, giữ ghi nhận người kiểm và kết luận thực tế trong README, rồi đóng gói lại. Không sửa scripts/ gốc.

Kết quả bộ kiểm gốc trước export: 17 PASS, 0 FAIL; PASS chỉ xác nhận định dạng và tính nhất quán. Không sửa nhãn hoặc lô v1 để vượt kiểm tra.

## Phối hợp với trưởng nhóm

submission/lineage.jsonl trong nhánh này gồm inject, train R-021, decision HOLD v1 và release v2 có parent. Máy thực hiện export cuối cần dùng đúng lịch sử này (hoặc bản gộp giữ đủ sự kiện), tránh ghi đè bằng lineage cũ. Không ghi sự kiện trùng.

security.md nêu ảnh 000000020992.jpg làm minh họa ca khuôn mặt; TV5 cần kiểm lại minh họa trước khi nộp. Chưa ghi nhận đã báo người phụ trách hoặc đã xử lý làm mờ. Các file errors/review/trace là bản nhóm cung cấp; trưởng nhóm xác nhận không có bản mới trước lần nộp cuối.

Các kết quả đã export nằm trong submission/r36/. Không commit runs/, data_source/, ZIP hoặc delivery v1. Khi nội dung v2 đổi, cập nhật manifest nếu ảnh/nhãn đổi, đóng gói lại, chạy kiểm tra rồi export lại.

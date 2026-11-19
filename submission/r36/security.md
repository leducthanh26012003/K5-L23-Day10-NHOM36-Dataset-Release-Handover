# Bảo mật khi làm việc — Nhóm 36

Người phụ trách: Phạm Trần Anh (TV5). Seed: 36. Lô v1: `lab250_3c9a0e0e4b9c`; bản bàn giao detection: `lab250_3c9a0e0e4b9c_v2`.

Bản v2 hiện gồm 240 ảnh và 1.681 nhãn; 10 ảnh cần rework được tách khỏi v2. Việc loại lỗi nhãn không tự giải quyết yêu cầu bảo mật. Kết luận v2 hiện giữ Hold để chờ hoàn tất kiểm tra và quyết định của người phụ trách.

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp

Tôi không tự chép lô dữ liệu ra USB hoặc gửi qua email, tài khoản lưu trữ cá nhân. Những cách này đưa dữ liệu ra ngoài môi trường được quản lý, khó kiểm soát ai truy cập, sao chép và lưu giữ. Nhờ người ngoài làm hộ cũng làm lộ dữ liệu và không bảo đảm người đó có quyền tham gia dự án.

Tôi lưu tiến độ trong hệ thống được cấp quyền, khóa hoặc đăng xuất máy theo quy định và báo người phụ trách nếu cần thêm thời gian. Nếu cần làm từ xa, tôi chỉ dùng môi trường và phương thức được đơn vị phê duyệt, đúng quyền được giao; nếu chưa có thì tiếp tục tại nơi làm việc vào thời gian được cho phép.

## 2. Năm việc: được hay không

| Hành động | Kết luận | Lý do và cách xử lý |
|---|---|---|
| Mở job được giao trên máy công ty | Được, trong phạm vi được cấp quyền | Dùng tài khoản riêng và công cụ được phê duyệt, chỉ mở dữ liệu phục vụ nhiệm vụ được giao. |
| Chụp màn hình gửi người quen | Không | Ảnh chụp vẫn chứa dữ liệu dự án; người quen không có quyền truy cập. Nếu cần hỗ trợ, trao đổi qua kênh nội bộ với người có thẩm quyền. |
| Chép lô ra USB cá nhân | Không tự thực hiện | Việc sao chép làm dữ liệu rời môi trường kiểm soát. Chỉ chuyển dữ liệu bằng quy trình, thiết bị và quyền được phê duyệt. |
| Dán nhãn thật của dự án lên chatbot bên ngoài | Không tự thực hiện | Nhãn, ảnh hoặc metadata có thể là dữ liệu nội bộ. Chỉ dùng dữ liệu giả hoặc công cụ và dữ liệu được đơn vị cho phép. |
| Đưa tài khoản CVAT cho đồng nghiệp | Không | Mất khả năng truy trách nhiệm thao tác và có thể vượt quyền. Đồng nghiệp cần tài khoản riêng, được cấp đúng job. |

Trong lab này, ảnh COCO là công khai và quy tắc bài cho phép hỏi AI với dữ liệu đó nếu ghi prompts.md. Quyền này không tự áp dụng cho dữ liệu thật của dự án; kết luận review trong lab vẫn phải do thành viên trực tiếp xem ảnh đưa ra.

## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ

Tôi đặt trạng thái lô là Hold và báo người phụ trách dữ liệu/bảo mật qua kênh được phê duyệt. Báo cáo cần chỉ rõ mã ảnh, vị trí khuôn mặt và yêu cầu guideline liên quan để người phụ trách xác nhận phạm vi xử lý. Tôi không tự làm mờ hay xóa ảnh vì có thể làm thay đổi bằng chứng, phá vỡ khả năng truy vết hoặc xử lý sai phạm vi; đặc biệt không sửa delivery v1. Việc xử lý được giao cho đúng người, tạo phiên bản mới và kiểm tra lại trước khi quyết định phát hành.

Ví dụ cụ thể trong lô: `000000020992.jpg`, có trong cả delivery v1 và v2. Ảnh chụp cận một người đang cầm đồ ăn gần miệng; khuôn mặt chiếm phần lớn vùng giữa và bên phải ảnh, thấy rõ mắt, mũi và miệng. Đây là ảnh minh họa được đề xuất cho ca yêu cầu làm mờ khuôn mặt; không phải một kết luận confirmed/rejected về nhãn detection.

Với giả định guideline của ca bảo mật yêu cầu làm mờ khuôn mặt, tôi giữ lô ở trạng thái Hold, đưa mã ảnh này và yêu cầu liên quan vào thông tin cần báo. Người phụ trách TV5 kiểm lại ảnh minh họa trước khi gửi báo cáo hoặc nộp bài. Chưa ghi nhận đã xử lý làm mờ hay đã gửi thông báo.

Đầu mối đề xuất: báo trưởng nhóm Lê Đức Thanh để chuyển tới người phụ trách dữ liệu/bảo mật theo kênh được phê duyệt. Đây là phương án xử lý, không phải ghi nhận đã gửi báo cáo. Chỉ cập nhật trạng thái sau khi yêu cầu được xử lý và người có thẩm quyền duyệt.

Xác nhận ảnh wrong_hash `000000001993` mở bình thường chỉ phục vụ xử lý hash; không được dùng thay cho quan sát khuôn mặt.

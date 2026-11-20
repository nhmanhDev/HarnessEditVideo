# Kiến trúc

Ảnh chụp hiện tại của hệ thống. Sửa đè tại chỗ khi đổi cấu trúc; lịch sử nằm ở CHANGELOG.md. Chỉ ghi điều đã đúng với mã đang chạy.

## Tổng quan
Repo mới được dựng khung từ mẫu docs-only của SecondBrain. Chưa có mã ứng dụng. Mục tiêu: Claude Code đọc thư mục video gốc và video mẫu rồi dựng video thành phẩm theo quy tắc riêng.

## Thành phần
Chưa có. Khi có module đầu tiên, ghi mỗi module một dòng: tên, vai trò, cổng (nếu có; lấy từ Port Table của SecondBrain).

## Luồng dữ liệu
Chưa có.

## Dữ liệu
Chưa có. Video gốc, video mẫu và video thành phẩm là dữ liệu chạy, không đưa vào repo.

## Triển khai
Chưa có. Repo có kind lib trong .ai42e.json nên chưa cần Docker; khi có backend hoặc web thì bổ sung theo chuẩn trong Rules/Repo Scaffold.md của SecondBrain.

## Giới hạn và mục tiêu tải
Chưa đo.

## Việc chưa làm
- Chọn stack và cấu trúc thư mục code theo loại agent hoặc công cụ dòng lệnh.
- Thư mục làm việc video và skill chỉnh sửa đầu tiên.
- Workflow CI trong .github/workflows/ chạy test và kiểm chuẩn khi mở PR vào dev.

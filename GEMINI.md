# GEMINI.md

Đọc SecondBrain theo đường dẫn trong chỉ dẫn global đã được bộ `_Setup/Setup-SecondBrain.ps1` thiết lập. Nếu chưa có biển trỏ hoặc không đọc được vault, báo thiếu cấu hình; không tự đoán đường dẫn máy.
Sau đó đọc `Rules/AI Repo Rules.md` trong vault trước khi làm việc ở repo code.

## Quy tắc dự án

- Repo: `HarnessEditVideo` (GitHub: `nhmanhDev/HarnessEditVideo`): harness để Claude Code edit video theo quy trình và phong cách riêng của chủ repo. Đang ở giai đoạn dựng khung; chưa có tính năng chạy được.
- Stack, lệnh chạy/test và các giới hạn riêng: chưa chọn stack (chưa có mã). Test: `node --test`. Kiểm chuẩn: `node scripts/check-standard.mjs .`.
- Luật chung (git, docs, UI, tên) nằm ở SecondBrain: `Rules/AI Repo Rules.md`; không sao chép dài vào đây. Mấy điều sau áp dụng ngay cả khi không đọc được vault:
  - Xong việc chạy `node scripts/check-standard.mjs .` và sửa lỗi thuộc phạm vi.
  - Ghi `docs/CHANGELOG.md` và `docs/JOURNAL.md` đúng bảng và giới hạn ghi ở đầu mỗi file (JOURNAL tối đa 40 dòng).
  - Tên file, thư mục, nhánh, dòng đầu commit: tiếng Anh không dấu (`feat/dropdown-token`, `feat(ui): add dropdown tokens`); nội dung docs và giao diện: tiếng Việt.
  - Nhánh làm việc từ `dev`, PR vào `dev`, không tự merge; không đường dẫn tuyệt đối theo máy trong file commit.

## Workflow Plan → triển khai → review

Nêu plan trước khi sửa, triển khai trong phạm vi, rồi kiểm tra diff và chạy kiểm chứng phù hợp. Nếu runtime hỗ trợ reviewer riêng và task có yêu cầu, dùng reviewer; nếu tự review trong cùng phiên thì ghi rõ đây không phải review độc lập.
```

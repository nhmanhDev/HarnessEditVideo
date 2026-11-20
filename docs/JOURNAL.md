# JOURNAL — việc đang dở (xong thì xoá, ghi vào CHANGELOG; tối đa ~40 dòng)

Mục mới ở trên cùng: `### YYYY-MM-DD — [tool] — tiêu đề`, rồi đã làm tới đâu / còn thiếu gì / người sau cần biết gì.

## Log
### 2026-11-20 — [claude-code] — agent dựng video v0, chờ khóa và nhạc để kiểm
- Đã làm: pipeline đầy đủ, 24 test pass, ruff sạch, chạy thật trên reel (loại 1 và loại 2 đều ra file đúng 1080x1920).
- Chưa kiểm: lập kế hoạch bằng Claude (cần ANTHROPIC_API_KEY); lời đọc TTS (cần OPENAI_API_KEY); nhạc có giấy phép (chưa có file nào; trang OpenGameArt trả 403 khi tải tự động, không thử lại trang đó).
- Chưa có: thư viện nhạc, font kiểm trên máy khác, Drive riêng tư.
- Nhánh feat/edit-agent-v0 đi từ dev. PR #4 (scaffold) chưa merge, cả hai cùng tạo CHANGELOG, JOURNAL, ARCHITECTURE, .gitignore, .env.example: khi merge #4 có thể xung đột, cần gộp tay.

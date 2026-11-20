# Nhật ký thay đổi

Mục mới nhất ở đầu. Một dòng một việc đáng kể (fix hoặc tính năng). Ngày là ngày làm xong, dạng `YYYY-MM-DD`. Ghi nguyên nhân gốc, không chỉ triệu chứng; giải pháp nêu rõ file, lệnh hoặc giá trị đã đổi. Giữ file dưới 400 dòng: quá thì chuyển phần cũ sang `docs/archive/`.

| Ngày | Lỗi hoặc thay đổi | Nguyên nhân | Giải pháp |
|------|-------------------|-------------|-----------|
| 2026-11-20 | Dựng khung repo từ mẫu docs-only: README, LICENSE Apache-2.0, CLAUDE/AGENTS/GEMINI, docs, test xương sống | Repo GitHub mới tạo còn rỗng, chưa có file chuẩn | Chạy scaffold.mjs --type docs-only, điền placeholder, lấy LICENSE từ GitHub API, thêm tests/scaffold.test.mjs |

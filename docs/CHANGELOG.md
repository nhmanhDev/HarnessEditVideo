# Nhật ký thay đổi

Mục mới nhất ở đầu. Một dòng một việc đáng kể. Ngày là ngày làm xong, dạng YYYY-MM-DD.

| Ngày | Lỗi hoặc thay đổi | Nguyên nhân | Giải pháp |
|------|-------------------|-------------|-----------|
| 2026-11-20 | Thêm agent dựng video v0: nhận video, nhận dạng giọng nói, lập kế hoạch bằng Claude, dựng bằng ffmpeg | Mục tiêu: agent đọc và dựng video reel từ link Drive, hai loại đầu ra (chữ và nhạc; có lời, nhạc và phụ đề) | Thêm `src/edit_agent/` (pipeline, policy, render, planner, tts, transcribe), CLI `edit-agent`, 24 test (pytest), CI Python |

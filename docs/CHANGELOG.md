# Nhật ký thay đổi

Mục mới nhất ở đầu. Một dòng một việc đáng kể. Ngày là ngày làm xong, dạng YYYY-MM-DD.

| Ngày | Lỗi hoặc thay đổi | Nguyên nhân | Giải pháp |
|------|-------------------|-------------|-----------|
| 2026-11-20 | Video thử ra âm lượng lệch và im lặng dài (loại 1 -19 LUFS; loại 2 im lặng 10,85 giây); nhịp cắt quá chậm; khung ngang bị cắt mất hai bên | Chưa có bước chuẩn âm lượng, chưa có nhạc nền khi thiếu tiếng, đoạn chọn chưa khớp nhịp mẫu, khung luôn cắt giữa | Thêm `edit-agent qa` (đo bằng số, ngưỡng hiệu chỉnh từ 6 reel mẫu, `docs/QA.md`); `loudnorm -14 LUFS` và fade nhạc trong `render.py`; nhạc nền tự đặt khi lời đọc dưới 70% thời lượng; nền mờ `fit=blur`; kích thước mặc định 1440x2560; `cuts.json` ghi điểm cắt thật |
| 2026-11-20 | Thêm agent dựng video v0: nhận video, nhận dạng giọng nói, lập kế hoạch bằng Claude, dựng bằng ffmpeg | Mục tiêu: agent đọc và dựng video reel từ link Drive, hai loại đầu ra (chữ và nhạc; có lời, nhạc và phụ đề) | Thêm `src/edit_agent/` (pipeline, policy, render, planner, tts, transcribe), CLI `edit-agent`, 24 test (pytest), CI Python |

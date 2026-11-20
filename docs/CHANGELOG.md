# Nhật ký thay đổi

Mục mới nhất ở đầu. Một dòng một việc đáng kể. Ngày là ngày làm xong, dạng YYYY-MM-DD.

| Ngày | Lỗi hoặc thay đổi | Nguyên nhân | Giải pháp |
|------|-------------------|-------------|-----------|
| 2026-11-20 | Giọng ILABY đọc sai nhiều từ (Vietnamese); mặc định engine vieneu | Mặc định trong code là vieneu; chưa đo engine | Đặt mặc định omnivoice (đo 1 lần: 65% so với 42%); đo lặp 3 lần thì tốc độ 0,8 không tốt hơn 1,0 (69% so với 73%), nên giữ 1,0. Bản render hiện tại đạt 73% số từ khớp. Chưa đạt chuẩn đọc chính xác; cần mẫu giọng sạch hơn để cải thiện |
| 2026-11-20 | Chữ trên video thô (tĩnh, không chuyển động, phụ đề hiện cả câu một lúc) | Tiêu đề và phụ đề chỉ là drawtext cố định, không có biểu thức theo thời gian | `motion.py`: tiêu đề hiện dần (mờ vào, trượt lên, phóng nhẹ, mờ ra) với font đậm nếu có; phụ đề hiện từng từ theo nhịp lời; test trong `tests/test_motion.py`. 49 test pass |
| 2026-11-20 | Video thử ra âm lượng lệch và im lặng dài (loại 1 -19 LUFS; loại 2 im lặng 10,85 giây); nhịp cắt quá chậm; khung ngang bị cắt mất hai bên | Chưa có bước chuẩn âm lượng, chưa có nhạc nền khi thiếu tiếng, đoạn chọn chưa khớp nhịp mẫu, khung luôn cắt giữa | Thêm `edit-agent qa` (đo bằng số, ngưỡng hiệu chỉnh từ 6 reel mẫu, `docs/QA.md`); `loudnorm -14 LUFS` và fade nhạc trong `render.py`; nhạc nền tự đặt khi lời đọc dưới 70% thời lượng; nền mờ `fit=blur`; kích thước mặc định 1440x2560; `cuts.json` ghi điểm cắt thật |
| 2026-11-20 | Thêm agent dựng video v0: nhận video, nhận dạng giọng nói, lập kế hoạch bằng Claude, dựng bằng ffmpeg | Mục tiêu: agent đọc và dựng video reel từ link Drive, hai loại đầu ra (chữ và nhạc; có lời, nhạc và phụ đề) | Thêm `src/edit_agent/` (pipeline, policy, render, planner, tts, transcribe), CLI `edit-agent`, 24 test (pytest), CI Python |

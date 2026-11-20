# JOURNAL — việc đang dở (xong thì xoá, ghi vào CHANGELOG; tối đa ~40 dòng)

Mục mới ở trên cùng: `### YYYY-MM-DD — [tool] — tiêu đề`, rồi đã làm tới đâu / còn thiếu gì / người sau cần biết gì.

## Log
### 2026-11-21 — [claude-code] — Chọn lại đoạn bằng ảnh dày, model chấm 8/10 trên 14 clip
- Đã làm: `refine.py` (model xem khung mỗi 0,3 giây quanh từng đoạn, chọn lại điểm bắt đầu), khoảng yên vị, lệnh `edit-agent refine`. Bản tốt: `workspace/ket-qua/loai1-14clip-diem8.mp4` (18,3 giây, QA đạt). Điểm 6 → 7 → 8 do model Claude chấm, không phải người.
- Còn thiếu: chỉ thử loại 1 trên một bộ clip; critic nói chưa xem hết ảnh nguồn; loại 2 chưa chạy lại với refine; giọng ILABY còn khoảng 70% từ khớp; chưa chạy bằng API Anthropic hay model khác (chỉ backend claude-cli); video ra 18 giây, chưa thử dài hơn.
- Người sau cần biết: lỗi model (hết hạn mức) từng bị nuốt im lặng nên bước chọn lại trông như không đổi; nay in cảnh báo. Có `agent-job` để chạy lại trên job đã chuẩn bị.
### 2026-11-20 — [claude-code] — QA và nâng cấp chất lượng, còn chọn đoạn bằng tay
- Đã làm: `edit-agent qa` (đo bằng số), ngưỡng hiệu chỉnh từ 6 reel mẫu (`docs/QA.md`); `loudnorm -14 LUFS`, fade nhạc, nền mờ, 1440x2560, nhạc tự đặt khi thiếu tiếng; 42 test pass.
- Kết quả: loại 1 (nhạc Pixabay) ĐẠT 17,6 giây; loại 2 (lời Voice Studio) ĐẠT 13,5 giây. Đều trong `workspace/jobs/`.
- Còn thiếu: chọn đoạn còn bằng tay, vài khung rèm trống ở đầu đoạn; chưa chấm chất lượng bằng mắt cho nhiều clip; loại 2 mới một clip; chưa chạy model Claude thật; chưa so model.
- Việc kế: chọn đoạn tự động theo độ chi tiết khung hình; chạy 3 đến 5 clip Drive khác; so 2 model khi có khóa Claude (đo bằng `bench-agent`).
- Nhánh feat/edit-agent-v0 đi từ dev. PR #4 (scaffold) chưa gộp: hai PR cùng tạo CHANGELOG, JOURNAL, ARCHITECTURE, .gitignore, .env.example, .ai42e.json.

# JOURNAL — việc đang dở (xong thì xoá, ghi vào CHANGELOG; tối đa ~40 dòng)

Mục mới ở trên cùng: `### YYYY-MM-DD — [tool] — tiêu đề`, rồi đã làm tới đâu / còn thiếu gì / người sau cần biết gì.

## Log
### 2026-11-21 — [claude-code] — Chọn lại đoạn bằng ảnh dày, model chấm 8/10 trên 14 clip
- Đã làm: `refine.py` (model xem khung mỗi 0,3 giây quanh từng đoạn, chọn lại điểm bắt đầu), khoảng yên vị, lệnh `edit-agent refine`. Bản tốt: `workspace/ket-qua/loai1-14clip-diem8.mp4` (18,3 giây, QA đạt). Điểm 6 → 7 → 8 do model Claude chấm, không phải người.
- Loại 2 (giọng ILABY, nhạc, phụ đề) cũng chấm 8/10: `workspace/ket-qua/loai2-14clip-diem8.mp4` (16,9 giây, -13,7 LUFS, QA đạt). Giọng chọn bản tốt nhất trong tối đa 3 lần (`voicecheck.py`), độ khớp nghe lại 0,55 đến 1,0 (đa số 0,8 trở lên).
- Cập nhật cuối: số, % thành chữ cho TTS (độ khớp 0,85 đến 1,0 mọi câu), cờ `caption` cho lời đọc, loại 2 hai lần chấm độc lập đều 8/10 (`loai2-14clip-diem8.mp4`), bản dài 20 giây 8/10 (`loai2-14clip-dai-diem8.mp4`); nguồn chỉ có khoảng 10 bộ đồ khác nhau nên không dài hơn được mà không lặp.
- Thử bộ clip thứ hai (4 clip cinetran, loại 1): 5 đến 7/10 qua các lần chạy (cuối 6/10), QA đạt, 8 giây, chỉ 4 cảnh. Nguồn gần như chỉ có cảnh cuộn, mở banner và cảnh xa giữa phố (banner nhỏ, xe che) nên không đủ cảnh tốt; đây là giới hạn nội dung, harness không tạo thêm được. Đã sửa: vị trí chữ chọn theo khung (`vi_tri_chu` trong `refine.py`, chỉ áp ở vòng đầu để không ghi đè quyết định của critic).
- Đổi model qua cấu hình: `CLAUDE_MODEL=claude-opus-5-5` trên bộ chính, loại 1, ra 8/10 vòng 1 (cùng mức với model mặc định). Chưa thử API Anthropic trực tiếp (không có khoá) hay model hãng khác.
- Còn thiếu: tính tổng quát chưa đủ (bộ clip thứ hai 7/10); điểm do model chấm, dao động ±1 giữa các lần chạy, chưa có người xem; giọng ILABY vẫn có câu đọc sai (câu có số, tên Anh); chưa chạy bằng API Anthropic hay model khác (chỉ backend claude-cli); video ra 17 đến 18 giây; cảnh báo QA "cảnh dài 6 giây" là các đoạn liền cùng nền rèm, không phải đứng hình.
- Người sau cần biết: lỗi model (hết hạn mức) từng bị nuốt im lặng nên bước chọn lại trông như không đổi; nay in cảnh báo. Có `agent-job` để chạy lại trên job đã chuẩn bị.
### 2026-11-20 — [claude-code] — QA và nâng cấp chất lượng, còn chọn đoạn bằng tay
- Đã làm: `edit-agent qa` (đo bằng số), ngưỡng hiệu chỉnh từ 6 reel mẫu (`docs/QA.md`); `loudnorm -14 LUFS`, fade nhạc, nền mờ, 1440x2560, nhạc tự đặt khi thiếu tiếng; 42 test pass.
- Kết quả: loại 1 (nhạc Pixabay) ĐẠT 17,6 giây; loại 2 (lời Voice Studio) ĐẠT 13,5 giây. Đều trong `workspace/jobs/`.
- Còn thiếu: chọn đoạn còn bằng tay, vài khung rèm trống ở đầu đoạn; chưa chấm chất lượng bằng mắt cho nhiều clip; loại 2 mới một clip; chưa chạy model Claude thật; chưa so model.
- Việc kế: chọn đoạn tự động theo độ chi tiết khung hình; chạy 3 đến 5 clip Drive khác; so 2 model khi có khóa Claude (đo bằng `bench-agent`).
- Nhánh feat/edit-agent-v0 đi từ dev. PR #4 (scaffold) chưa gộp: hai PR cùng tạo CHANGELOG, JOURNAL, ARCHITECTURE, .gitignore, .env.example, .ai42e.json.

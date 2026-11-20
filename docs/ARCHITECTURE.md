# Kiến trúc

Ảnh chụp hiện tại của hệ thống. Chỉ ghi điều đã đúng với mã đang có.

## Tổng quan
Agent nhận một video nguồn (link Drive công khai hoặc file cục bộ) và một loại đầu ra. Pipeline chạy tuần tự, mỗi bước ghi kết quả vào thư mục job để xem lại được.

## Luồng dữ liệu
1. `intake.py`: tải hoặc sao chép video nguồn vào `workspace/jobs/<job>/input/`.
2. `media.py` (ffprobe): đọc độ dài, kích thước, có âm thanh hay không.
3. `transcribe.py` (faster-whisper, chạy trên máy): tách âm thanh WAV 16 kHz rồi nhận dạng giọng nói.
4. `policy.py`: tìm các khoảng có lời gốc, tính ánh xạ thời gian nguồn sang đầu ra.
5. `media.py`: lấy khung hình đều nhau (tối đa 30) để gửi cho model.
6. `planner.py` (Claude API): nhận khung hình, transcript và yêu cầu, trả về JSON kế hoạch (`spec.EditPlan`). Kiểm đúng schema, lỗi thì thử lại một lần.
7. `policy.py`: kiểm quy tắc giọng nói, bỏ lời đọc trùng lời gốc, tắt tiếng gốc cho loại 1, lọc nhạc không có giấy phép, dựng phụ đề từ transcript.
8. `tts.py`: tạo lời đọc cho các dòng được phép (adapter, bản đầu dùng OpenAI).
9. `render.py` (ffmpeg): ghép các đoạn cắt, khung 9:16, chữ, phụ đề, lời đọc, nhạc có ducking khi còn tiếng nói.
10. Ghi `plan.json` và `report.md` vào thư mục job.

## Thành phần
| Module | Vai trò |
|---|---|
| `spec.py` | Hợp đồng dữ liệu: `JobSpec` (yêu cầu) và `EditPlan` (kế hoạch) |
| `config.py` | Đọc `.env`, thư mục làm việc, tìm font có dấu và ffmpeg |
| `policy.py` | Mọi quy tắc giọng nói và ánh xạ thời gian; model đề xuất, module này quyết định |
| `render.py` | Xây đồ thị ffmpeg. Không dùng đường dẫn tuyệt đối trong lệnh |
| `planner.py` | Gọi Claude và kiểm đầu ra |
| `tts.py` | Adapter giọng đọc |
| `music.py` | Thư viện nhạc có giấy phép |

## Dữ liệu
Toàn bộ dữ liệu chạy nằm trong `workspace/` (không commit): video, khung hình, transcript, nhạc, kết quả. Prompt của model nằm ở `templates/planner-system.md`.

## Triển khai
Chạy trên máy cá nhân. Chưa có Docker vì đây là công cụ dòng lệnh, không phải dịch vụ.

## Kiểm thử
- `uv run pytest`: quy tắc giọng nói, schema, đồ thị ffmpeg, parse JSON của planner, và một lần dựng thật bằng ffmpeg trên clip tạo sẵn.
- CI (`.github/workflows/python.yml`) chạy ruff và pytest khi mở PR vào `dev`.

## Giới hạn hiện tại
- Chưa kiểm lập kế hoạch bằng Claude trên video thật (chưa có khóa).
- Chưa kiểm lời đọc TTS (chưa có khóa OpenAI được dùng thử).
- Chưa có thư viện nhạc có giấy phép. Pipeline nhạc đã được viết nhưng chưa chạy với file nhạc thật.
- Drive riêng tư (tài khoản dịch vụ) chưa hỗ trợ; chỉ link công khai.
- Phiên âm tiếng Việt của Whisper cỡ `small` có lỗi nhận dạng (ví dụ "clod" thay cho "Claude"). Nên kiểm phụ đề trước khi dùng.

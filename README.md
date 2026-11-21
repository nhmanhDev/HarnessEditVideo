# HarnessEditVideo

[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)
![Lang](https://img.shields.io/badge/Python-3.12-informational?style=flat-square)

Agent dựng video dọc (reel) từ một video nguồn: đọc nội dung, lập kế hoạch cắt ghép bằng Claude, rồi dựng bằng ffmpeg. Có hai loại đầu ra:

- **Loại 1 (`text_music`)**: chữ trên video và nhạc nền, không có lời.
- **Loại 2 (`speech_music_caption`)**: giữ lời gốc, nhạc nền, và phụ đề tuỳ chọn.

> Trạng thái: prototype đã chạy end-to-end trên video thật. Đã thử lập/chỉnh kế hoạch bằng Claude CLI, TTS, phụ đề, QA và render trên các bộ clip. Điểm chất lượng hiện do model tự chấm; cần người xem đánh giá thêm và thử trên nhiều nguồn hơn.

## Cài đặt
Yêu cầu: Python 3.12, [uv](https://docs.astral.sh/uv/), ffmpeg và ffprobe trong PATH.

```sh
uv sync --extra dev
cp .env.example .env   # điền ANTHROPIC_API_KEY, OPENAI_API_KEY nếu dùng lời đọc
uv run edit-agent check
```

`check` in ra trạng thái từng công cụ và khóa. Dòng nào báo THIẾU thì cần bổ sung.

## Cách dùng
Đầu vào có thể là: link file Drive, link **thư mục** Drive (nhiều clip), file cục bộ, hoặc thư mục cục bộ. Drive phải để "Bất kỳ ai có đường liên kết". Thư mục nhiều clip được gộp thành một nguồn, model chọn đoạn trải đều qua các clip và không cắt vượt ranh giới clip.

Chạy trọn vẹn, model tự làm đến khi đạt (lập kế hoạch, dựng, đo QA, tự xem lại và sửa, chọn bản tốt nhất):

```sh
uv run edit-agent agent --input "<link hoặc đường dẫn>" --type text_music --rounds 2
uv run edit-agent agent --input "<link hoặc đường dẫn>" --type speech_music_caption --captions --language vi
```

Model là phần thay được. Mặc định là Claude Code không giao diện (`PLANNER=claude-cli`, đặt `CLAUDE_BIN` trỏ tới `claude.exe`, dùng quota Claude Code, không cần API key). Đổi sang Claude API bằng `--backend anthropic` (cần `ANTHROPIC_API_KEY`), hoặc lệnh ngoài đọc prompt từ stdin bằng `--backend command` và `PLANNER_CMD` (Codex, Gemini...). Kết quả mỗi vòng nằm trong thư mục job (`final_r0.mp4`, `plan_r0.json`, `agent_report.md`), bản chọn là `final_best.mp4`.

Chạy từng bước với kế hoạch tự viết hoặc kế hoạch có sẵn (không dùng model):

```sh
uv run edit-agent prepare --input "<link hoặc đường dẫn>" --type text_music
uv run edit-agent render --job "<thư mục job>" --planner manual
```

Kiểm chất lượng bằng số (âm lượng, đỉnh, im lặng, khung đen, đứng hình, nhịp cắt). Chi tiết ngưỡng và số đo mẫu: [docs/QA.md](docs/QA.md):

```sh
uv run edit-agent qa "<file mp4>" --out workspace/qa/bao-cao.json
```

Chọn lại điểm bắt đầu và vị trí chữ theo ảnh khung hình dày của từng đoạn:

```sh
uv run edit-agent refine --job "<thư mục job>"
```

Lệnh `agent` gọi bước refine trong mỗi vòng dựng. Dùng `render --refined` để dựng kế hoạch đã refine mà không áp dụng dịch chuyển đoạn lần nữa.

Chạy với kế hoạch có sẵn (bỏ qua Claude, dùng để kiểm thử):

```sh
uv run edit-agent run --input "<file>" --type text_music --plan plan.json
```

Mỗi job tạo một thư mục trong `workspace/jobs/`: `final.mp4`, `report.md` (kèm cảnh báo các quy tắc đã bỏ), `plan.json`, `transcript.json`.

## Quy tắc về giọng nói
- Không bao giờ đọc lời đè lên lời gốc đang phát. Lời đọc trùng bị bỏ và ghi vào báo cáo.
- Video nguồn không có lời thì không tạo lời gốc; tiếng gốc bị tắt.
- Loại 1 luôn tắt tiếng gốc và không có lời đọc.

## Nhạc nền
Đặt file nhạc trong `workspace/music/` kèm `manifest.json`. Mỗi bài phải có `license` và `source`; bài thiếu giấy phép sẽ bị bỏ qua. Mẫu: [templates/music-manifest.example.json](templates/music-manifest.example.json).

## Kiến trúc
Xem [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Đóng góp & bảo mật
- Đóng góp: xem hướng dẫn tạo nhánh và PR trong GitHub.
- Báo lỗi bảo mật: mở issue riêng tư theo tính năng Security của GitHub.

## License
Phát hành theo [Apache-2.0](LICENSE).

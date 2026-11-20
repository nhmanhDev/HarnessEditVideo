# HarnessEditVideo

[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)
![Lang](https://img.shields.io/badge/Python-3.12-informational?style=flat-square)

Agent dựng video dọc (reel) từ một video nguồn: đọc nội dung, lập kế hoạch cắt ghép bằng Claude, rồi dựng bằng ffmpeg. Có hai loại đầu ra:

- **Loại 1 (`text_music`)**: chữ trên video và nhạc nền, không có lời.
- **Loại 2 (`speech_music_caption`)**: giữ lời gốc, nhạc nền, và phụ đề tuỳ chọn.

> Trạng thái: bản thử đầu tiên. Đã kiểm pipeline với kế hoạch viết tay trên video thật. Chưa kiểm lập kế hoạch bằng Claude và lời đọc TTS, vì chưa có khóa API.

## Cài đặt
Yêu cầu: Python 3.12, [uv](https://docs.astral.sh/uv/), ffmpeg và ffprobe trong PATH.

```sh
uv sync --extra dev
cp .env.example .env   # điền ANTHROPIC_API_KEY, OPENAI_API_KEY nếu dùng lời đọc
uv run edit-agent check
```

`check` in ra trạng thái từng công cụ và khóa. Dòng nào báo THIẾU thì cần bổ sung.

## Cách dùng
Link Google Drive phải để "Bất kỳ ai có đường liên kết". Hoặc truyền đường dẫn file cục bộ.

```sh
uv run edit-agent run --input "<link hoặc đường dẫn>" --type text_music
uv run edit-agent run --input "<link hoặc đường dẫn>" --type speech_music_caption --captions --language vi
```

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
- Đóng góp: [CONTRIBUTING.md](CONTRIBUTING.md) (khi có)
- Báo lỗi bảo mật: [SECURITY.md](SECURITY.md) (khi có)

## License
Phát hành theo [Apache-2.0](LICENSE).

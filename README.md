# HarnessEditVideo

[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)
![Lang](https://img.shields.io/badge/Claude%20Code-informational?style=flat-square)

Harness để Claude Code edit video theo quy trình và phong cách riêng: đặt video gốc, video mẫu và video thành phẩm vào thư mục làm việc, rồi để agent dựng bản đầu, sau đó chỉnh theo phản hồi và ghi lại thành quy tắc.

> Trạng thái: đang dựng khung repo. Chưa có tính năng chạy được.

## Tính năng
Dự kiến, chưa làm:
- Thư mục làm việc chuẩn: video gốc, video mẫu, video thành phẩm.
- Skill chỉnh sửa video đi kèm, học dần từ phản hồi.
- Editor nhỏ để chỉnh màu chữ, phụ đề và âm thanh mà không tốn token mỗi lần.

## Cài đặt / Chạy local
Hiện chưa có gì để cài. Chạy kiểm tra của repo:
```sh
node --test
node scripts/check-standard.mjs .
```
Yêu cầu: Node.js 20 trở lên.

## Cách dùng
Chưa có. Mục này sẽ được bổ sung khi có skill đầu tiên.

## Kiến trúc
Repo chưa có mã ứng dụng. Chi tiết và tiến độ: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Đóng góp & bảo mật
- Đóng góp: [CONTRIBUTING.md](CONTRIBUTING.md)
- Báo lỗi bảo mật: [SECURITY.md](SECURITY.md)

## License
Phát hành theo [Apache-2.0](LICENSE).

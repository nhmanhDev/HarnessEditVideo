# Kiểm chất lượng (QA)

Đo bằng số, không cảm tính. Lệnh: `uv run edit-agent qa <file> [--out báo_cáo.json] [--silent]`. `--silent` dùng cho video không có tiếng là đúng.

## Cái đo được
| Chỉ số | Cách đo | Ngưỡng (LỖI nếu vượt) |
|---|---|---|
| Khung dọc | độ phân giải | cao hơn rộng, rộng từ 540 px |
| Âm lượng tích hợp | ebur128 | -16 đến -12 LUFS |
| Đỉnh thực | ebur128 peak | không quá -0,1 dBTP |
| Im lặng | silencedetect (dưới -45 dB, từ 1 giây) | tổng dưới 1 giây |
| Khung đen | blackdetect, bỏ qua thẻ kết cuối | tổng dưới 0,5 giây |
| Đứng hình | freezedetect (từ 1 giây) | một đoạn không quá 2 giây |
| Nhịp cắt | điểm cắt do pipeline ghi (`cuts.json`) hoặc đổi cảnh của ffmpeg | CẢNH BÁO: trung vị 1,2 đến 3,5 giây, cảnh dài nhất không quá 6 giây |

## Vì sao ngưỡng như vậy: số đo 6 reel mẫu đạt (2026-11-20)
Đo bằng `edit-agent qa` trên các reel mẫu, kết quả trong `workspace/qa/refs.json` (không đưa vào Git):

| Reel | Khung | Âm lượng (LUFS) | Đỉnh (dBTP) | Cắt | Cảnh trung vị (s) | Đứng hình tối đa (s) |
|---|---|---|---|---|---|---|
| 1529 | 1440x2560 | -14,1 | -3,9 | 4 | 4,84 | 1,6 |
| 1827 | 1440x2560 | -14,0 | -0,5 | 10 | 2,17 | 0,0 |
| 2231 | 1440x2560 | -14,0 | -2,0 | 5 | 3,46 | 1,4 |
| 2282 | 1440x2560 | -14,1 | -2,0 | 14 | 1,60 | 1,53 |
| 2523 | 1080x1920 | -14,1 | -0,8 | 1 | (một cảnh) | 0,0 |
| 4124 | 1080x1920 | -14,0 | -1,6 | 0 | (một cảnh) | 0,0 |

Kết luận: chuẩn giao là -14 LUFS (cả 6 reel đều đạt). Đỉnh thực có thể tới -0,5, nên ngưỡng chỉ chặn xén. Có reel đứng hình tới 1,6 giây khi giữ hình sản phẩm, nên ngưỡng đứng hình là 2 giây. Nhịp cắt là cảnh báo, không phải lỗi, vì 2 reel một cảnh vẫn đạt.

## Kết quả bản dựng thử (đầu vào: clip Drive, 1440x2560, nền mờ)
| Job | Trước (v2) | Sau (v5, đoạn chọn tự động) |
|---|---|---|
| Loại 1, có nhạc | -19,0 LUFS (quá nhỏ), 0 cắt, 22 giây | -14,6 LUFS, 7 cắt, trung vị 2,2 giây, đỉnh -1,2 dBTP, 17,6 giây, ĐẠT |
| Loại 2, lời đọc giọng ILABY | im lặng 10,85 giây, không nhạc, nhịp cắt 5 giây | -13,8 LUFS, im lặng 0, 5 cắt, trung vị 2,2 giây, đỉnh -2,6 dBTP, 13,2 giây, ĐẠT |

Đoạn chọn tự động (`edit_agent/select.py`) đo độ cạnh Laplacian mỗi nửa giây, chọn cửa sổ 2,2 giây có chi tiết cao nhất, không chồng nhau. Kiểm bằng mắt trên contact sheet: sản phẩm hiện ở gần như mọi khung, không còn đoạn rèm trống.

Lưu ý còn lại: vài khung đầu mỗi đoạn vẫn là rèm trống, vì chọn đoạn bằng tay từ contact sheet. Bước tiếp theo là chọn đoạn tự động theo độ chi tiết khung hình.

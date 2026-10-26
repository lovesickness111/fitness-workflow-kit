# Rà soát sau video thử `wall-hold-pilot` (2026-10-25)

Video thử: 9:16, 16,4 giây, 3 cảnh, 2 tư thế, giọng Genmax Adam, nhạc nền Lyria.
- Đi qua đủ các bước duyệt: kênh → nội dung → media → bản dựng.
- Bản cuối 1080×1920, −14,0 LUFS, đỉnh −1,5 dBFS.
- Chi phí: 190 credit Genmax cho lời đọc (cộng 544 credit cho 4 giọng mẫu) và 2 ảnh Gemini, không phải vẽ lại.

## Chỗ tốn thời gian và đã tối ưu

| Vấn đề trong lần thử | Đã sửa |
|---|---|
| Mỗi lần duyệt phải chép tay digest từ `review` sang `approve` | `review` tự lưu digest; `approve --decision ...` gắn vào đúng bản đã trình và từ chối nếu file đổi sau đó |
| Phải tự kẻ lưới bằng ffmpeg để đặt vị trí gân đỏ | `review/poses-grid.png` có lưới 10% kèm nhãn tọa độ |
| Phải gọi `stills` từng cảnh rồi tự ghép ảnh | `storyboard` tạo một ảnh gồm mọi cảnh ngay sau mỗi nhịp lời đọc (khoảng 10 s) |
| Chạy riêng audio, poses, sheet, stills | `produce` gộp các bước, tạo tư thế song song, báo cảnh có số nhịp lệch số câu và báo vị trí gân còn thiếu |
| Chạy riêng visuals, preview, rồi tự đo bằng ffmpeg | `build` render cảnh song song, ghép preview và tự đo kích thước, LUFS, đỉnh, mức nhạc giữa các cảnh, xuất bảng khung hình |
| Kiểm tra nguồn bằng tay qua Europe PMC | `research` tra DOI trên Crossref và so tiêu đề (ở lần thử: 2/2 nguồn khớp) |
| Không biết đã tiêu bao nhiêu | `status` báo credit Genmax và số ảnh Gemini |
| Đổi giọng làm mất lần duyệt nội dung | Giọng thuộc lần duyệt media; có 4 preset, mặc định Brian; mỗi video chọn được giọng riêng |
| Tường sát mép ảnh để lại đường cắt | Runtime làm mờ mép ảnh tư thế vào nền đen |

## Phát hiện cần bạn quyết định

1. **Nhạc nền gần như không nghe thấy giữa các cảnh** (đo được −50 dB).
   - Nguyên nhân: nhạc bị ép mạnh dưới giọng, trong khi khoảng nghỉ giữa các cảnh chỉ 0,35 s.
   - Đề xuất: tăng `gain_db` từ −22 lên khoảng −16 và ép nhẹ hơn. Việc này đổi hồ sơ kênh nên cần bạn đồng ý; không áp dụng ngược cho bản video thử đã duyệt.
2. **Chữ chạy 2 dòng chạm đỉnh đầu nhân vật** ở khung 9:16.
   - Đề xuất: hạ khung nhân vật xuống khoảng 2,5%. Chỉ ảnh hưởng video mới; video thử sẽ hiện trạng thái "STALE" nếu render lại.
3. **File khóa phiên bản motion-broll lệch từ trước.** Nên cập nhật trước khi bàn giao, vì khách sẽ thấy dòng ACTION trong `3-Kiem-tra.cmd`.

## Còn lại

- Chữ chạy từng từ: dùng Whisper chạy trên máy hoặc API speech-to-text của Genmax.
- Bài nhạc dài hơn 2:57 sẽ lặp lại từ đầu (`loop_start` chưa áp dụng); với Shorts thì chưa cần.
- Đăng bài video thử: cần bạn chọn nền tảng, chế độ công khai/riêng tư và duyệt caption.

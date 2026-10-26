# Video Workflow Kit

Bộ làm việc cho Windows, dùng với **Claude Desktop** (hoặc Codex):

- **Video fitness tạo mới:** từ một chủ đề, tạo trọn video giải thích tiếng Anh theo phong cách manga nền đen, gồm nhân vật, giọng đọc, đồng hồ, biểu đồ và chữ chạy.
- **Dựng video có sẵn:** cắt, ghép, thêm minh họa động cho video bạn đã quay.
- **Đăng bài:** lên TikTok, YouTube, Facebook, LinkedIn qua Zernio, sau khi bạn duyệt.

## Cần chuẩn bị

- Máy Windows 10/11 có mạng, còn trống khoảng 5 GB.
- **Claude Desktop** (tải ở claude.ai/download), đăng nhập bằng tài khoản Claude có dùng được Claude Code.
- Key dịch vụ theo nhu cầu (lấy trên trang của từng dịch vụ):
  - **Genmax**: giọng đọc tiếng Anh.
  - **Gemini**: vẽ ảnh dự phòng.
  - **Zernio**: đăng bài.
  - **ElevenLabs**: chuyển lời nói thành chữ cho video tự quay.
- Tùy chọn: tài khoản **ChatGPT**, dùng để vẽ ảnh nhân vật qua Codex. Không có thì kit vẽ bằng Gemini.

Ảnh minh họa cách đăng ký ElevenLabs, Zernio và tạo key có trong `docs/Huong-dan-su-dung.docx`. Phần mở thư mục trong tài liệu đó viết cho Codex; với Claude Desktop, làm theo bước 7 bên dưới.

## Cài đặt lần đầu

1. **Tải bộ kit:** mở trang GitHub của bộ kit, vào **Releases**, tải file `.zip` mới nhất. Cách khác: bấm nút **Code**, chọn **Download ZIP**.
2. **Giải nén:**
   - Trước khi giải nén, nhấp phải file ZIP, chọn **Properties**, tick **Unblock** rồi bấm **OK**. Nếu không thấy ô Unblock thì bỏ qua bước này.
   - Giải nén vào một thư mục cố định, đường dẫn ngắn, không dấu, không khoảng trắng, ví dụ `C:\VideoWorkflow`.
   - **Thư mục kit** là thư mục chứa file `1-Cai-dat.cmd`, thường là `C:\VideoWorkflow\video-workflow-kit`. Các bước sau đều làm trong thư mục này.
3. Bấm đúp **`1-Cai-dat.cmd`**. Nếu Windows hiện cảnh báo màu xanh, bấm **More info** rồi **Run anyway**. Bước này tự cài Python, Node.js, Git, FFmpeg và Codex CLI, mất vài phút, cần có mạng. Nếu Windows hỏi quyền cài đặt, chọn **Yes**.
4. Bấm đúp **`2-Nhap-key.cmd`**, rồi dán từng key và nhấn Enter. Ký tự sẽ không hiện ra khi gõ; key nào chưa có thì để trống.
5. Tùy chọn: bấm đúp **`4-Dang-nhap-Codex.cmd`** để đăng nhập ChatGPT, dùng cho việc vẽ ảnh.
6. Bấm đúp **`3-Kiem-tra.cmd`**. Dòng `OK` là đã sẵn sàng, dòng `ACTION` là việc cần làm thêm.
7. Mở **Claude Desktop**, chọn **Code**, chọn **thư mục kit** ở bước 2, rồi gửi:

   > Đọc START-HERE.md, kiểm tra máy đã sẵn sàng và hướng dẫn tôi từng bước. Chưa đăng bài.

   Khi Claude hỏi quyền chạy lệnh trong thư mục này, chọn **Allow**.

Key chỉ được lưu trên máy này (`local/secrets.env`), không đi vào Git hay file ZIP. Không gửi key cho ai, kể cả trong khung chat.

## Tạo video fitness

1. **Hồ sơ kênh** (làm một lần). Nhắn Claude:

   > Đọc skill fitness-explainer và tạo hồ sơ kênh cho tôi.

   - Gửi ảnh nhân vật của bạn (chính diện, nghiêng, cận mặt), hoặc để Claude vẽ vài phương án cho bạn chọn.
   - Nghe vài giọng mẫu rồi chọn giọng. Việc này tốn một ít credit, Claude sẽ hỏi trước.
2. **Mỗi video:** nói chủ đề, độ dài, và khung **9:16** hoặc **16:9**. Có thể gửi kèm một link YouTube để tham khảo cấu trúc và cách minh họa. Claude chỉ học cách làm, viết lời mới, dùng nhân vật của kênh bạn và kiểm chứng lại số liệu.
3. Mỗi video dừng ở **ba lần duyệt**, bạn chỉ cần trả lời "duyệt" hoặc nói cần sửa gì:
   - **Nội dung:** kịch bản đầy đủ, hướng minh họa, nguồn cho mọi số liệu.
   - **Media:** nghe `review/narration.mp3`, xem bảng ảnh và storyboard.
   - **Bản dựng:** xem `render/preview.mp4`.

   Sau đó Claude mới xuất `render/final.mp4`, kèm nháp mô tả khi đăng `render/description.md`.
4. Đăng bài là bước riêng: Claude trình caption, tài khoản, chế độ công khai và thời điểm, rồi chờ bạn duyệt.

Video đang làm dở: nói "tiếp tục video <tên>". Claude xem trạng thái bằng `tools\fitness_video.py status --project <tên>`. Hồ sơ kênh và nhân vật nằm trong `local/fitness/`, không đi vào Git.

## Dựng video có sẵn

1. Đặt video vào `projects\<ten-du-an>\input\`.
2. Nhắn Claude: "Đề xuất phương án edit cho video này." Bạn duyệt trước khi dựng, và xem bản dựng trước khi đăng.
3. Muốn có minh họa động cho vài đoạn: sau khi chốt bản cắt, nhắn "Đọc skill motion-broll và đề xuất 2–3 cảnh minh họa. Cho tôi duyệt trước khi render." Bản có minh họa được xuất riêng thành `edit/final-motion.mp4`; bản `edit/final.mp4` giữ nguyên.

## Các lệnh (cho người rành kỹ thuật)

```powershell
powershell -ExecutionPolicy Bypass -File .\setup\setup.ps1
powershell -ExecutionPolicy Bypass -File .\setup\configure.ps1
powershell -ExecutionPolicy Bypass -File .\setup\doctor.ps1
.venv\Scripts\python.exe tools\fitness_video.py doctor
node tools/publisher/dist/cli.js accounts
node tools/publisher/dist/cli.js check
```

- `accounts` và `check` gọi Zernio nhưng không đăng bài.
- `doctor` chỉ kiểm tra máy và cấu hình trên máy, không xác minh key với dịch vụ.

## Cập nhật

Chỉ dùng tag phiên bản do nhà cung cấp thông báo. `v1.1.0` dưới đây chỉ là ví dụ.

```powershell
powershell -ExecutionPolicy Bypass -File .\setup\update.ps1 -Component fitness-explainer -Version v1.1.0
powershell -ExecutionPolicy Bypass -File .\setup\update.ps1 -Component fitness-explainer -Rollback
```

Có thể dùng `-Source C:\duong-dan\bo-kit-moi` để cập nhật từ thư mục đã giải nén. Người bảo trì xem `docs/MAINTAINER.md`.

## Phạm vi và dữ liệu

- Python 3.11+, Node.js 22+, Git và FFmpeg (có bộ lọc `subtitles`); `1-Cai-dat.cmd` cài những thứ còn thiếu. Lần đầu chạy, phần render tải thêm Chromium vào `local/`.
- Chi phí tham khảo cho một video fitness khoảng 6–8 phút:
  - Genmax: khoảng 6.000 credit (1 credit cho mỗi ký tự lời đọc).
  - Ảnh: khoảng 15–20 ảnh (Codex khoảng 1–4 credit ChatGPT mỗi ảnh, hoặc Gemini khoảng $0,07 mỗi ảnh; chế độ chạy theo lô rẻ bằng nửa).
  - Render chạy trên máy, không tốn tiền.
- `local/`, `projects/` và `.venv/` không đi vào Git hoặc ZIP. Key trong `local/secrets.env` là văn bản thường trên ổ đĩa: giữ thư mục riêng tư và bảo vệ tài khoản Windows.
- Kit không kèm nhạc có bản quyền hay video của người khác. Dùng nhạc bạn có quyền sử dụng và ghi nguồn trong hồ sơ kênh.

Mã bộ kit do nhóm quản lý nội bộ. `video-use` và `motion-broll` giữ giấy phép riêng; xem `THIRD-PARTY-NOTICES.md`.

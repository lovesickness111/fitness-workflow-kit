# Ảnh trong tài liệu Word

Tài liệu Word hiện đã có ảnh người dùng chèn và ảnh đăng ký/API key từ nguồn chính thức. File Word là bản chính; thay ảnh trực tiếp bằng Change Picture. Giữ ảnh nguồn tại đây và ghi nguồn vào `SOURCES.md`. `tools/build_guide.py` chỉ tạo bản nháp riêng, không cập nhật nội dung thủ công trong tài liệu chính.

Các ảnh còn để bổ sung khi dùng tài khoản thực là `local-key-input.png` và `publish-review.png`. Chúng không thuộc phần đăng ký dịch vụ. Màn hình Connections trong ảnh Zernio chính thức đã minh họa cả Connect và trạng thái connected; không cần chèn lặp lại cùng ảnh.

| Tên file | Nội dung |
| --- | --- |
| github-download.png | Tải repo từ GitHub, do người dùng chụp |
| codex-new-project.png | Bấm dấu cộng tạo project trong Codex |
| codex-add-folder.png | Thêm folder nguồn vào project |
| codex-select-folder.png | Chọn folder video-workflow-kit |
| codex-setup-prompt.png | Gửi prompt thiết lập bộ kit |
| elevenlabs-sign-up.jpg | Form đăng ký ElevenLabs trống |
| elevenlabs-api-keys.png | ElevenLabs Developers → API Keys và nút Create API Key |
| elevenlabs-stt-permission.png | Form tạo key, Restrict Key bật, Speech to Text được Access, các quyền không dùng bị tắt |
| zernio-sign-up.jpg | Trang đăng ký Zernio |
| zernio-connect-accounts.png | Connections, nút Connect và trạng thái connected |
| zernio-create-key.png | Trang API Keys của Zernio và nút tạo key, không lộ key |
| local-key-input.png | Terminal configure.ps1 với ô nhập key ẩn, không có plaintext key |
| publish-review.png | Bản xem trước video và bảng duyệt caption, đích đăng, quyền riêng tư |

Chụp màn hình bằng Windows + Shift + S. Cắt vùng thao tác cần thiết, giữ nhãn/nút và phóng to đủ đọc. Che key bằng mảng đặc trước khi lưu, không chỉ làm mờ nhẹ. Không chụp mã 2FA, recovery code, cookie hoặc token. Không commit ảnh có dữ liệu bí mật. Tên menu có thể đổi; đối chiếu tài liệu chính thức khi chụp.

# Video Workflow Kit

Bộ làm việc Windows dùng với **Claude Desktop** (hoặc Codex):

- Tạo trọn video giải thích fitness tiếng Anh từ một chủ đề, bằng **fitness-explainer**.
- Chỉnh video có sẵn bằng **video-use**, tùy chọn thêm minh họa động bằng **motion-broll**.
- Đăng bản đã duyệt lên **YouTube, TikTok, Facebook hoặc LinkedIn** qua Zernio.

**Bắt đầu tại [START-HERE.md](START-HERE.md).**

## Cài nhanh

1. Tải file `.zip` mới nhất ở mục **Releases** của trang này, giải nén vào `C:\VideoWorkflow`.
2. Bấm đúp lần lượt `1-Cai-dat.cmd`, `2-Nhap-key.cmd` và `3-Kiem-tra.cmd`. Nếu muốn vẽ ảnh bằng tài khoản ChatGPT, chạy thêm `4-Dang-nhap-Codex.cmd`.
3. Mở Claude Desktop, chọn **Code**, chọn thư mục chứa `1-Cai-dat.cmd`, rồi gửi:

   > Đọc START-HERE.md, kiểm tra máy đã sẵn sàng và hướng dẫn tôi từng bước. Chưa đăng bài.

## Có trong bộ kit

- Sáu skill, Claude và Codex dùng chung:
  - `video-workflow`: điều phối;
  - `fitness-explainer`;
  - `video-use`;
  - `motion-broll`;
  - `social-publishing`;
  - `codex-image`: vẽ ảnh qua Codex, tính vào gói ChatGPT.
- `fitness-explainer` tạo video manga nền đen có HUD động, theo khung 9:16 hoặc 16:9:
  - giọng đọc Genmax, có 4 giọng sẵn;
  - ảnh nhân vật vẽ bằng Codex, dự phòng bằng Gemini (có chế độ chạy theo lô rẻ bằng nửa);
  - tham khảo nội dung và minh họa từ một video YouTube;
  - mọi số liệu có nguồn;
  - ba lần duyệt: nội dung, media, bản dựng.
- motion-broll tùy chọn sau khi chốt cut: xuất `edit/final-motion.mp4` riêng, không ghi đè bản gốc.
- Cài đặt Windows bằng cách bấm đúp. Key được nhập ẩn và chỉ lưu trên máy (`local/secrets.env`).
- Công cụ đăng MP4 có lịch sử và xử lý trường hợp đăng lỗi một phần.
- Khóa phiên bản, cập nhật và khôi phục riêng từng thành phần. Xem [hướng dẫn người bảo trì](docs/MAINTAINER.md).

Bộ kit không chứa API key, tài khoản, hồ sơ kênh, nhân vật, video hay nhạc của tác giả. Mỗi người dùng tự nhập key và kết nối tài khoản của mình.

Phiên bản 0.3.0 vẫn là **prerelease**: chưa chạy end-to-end trên một máy sạch. Xem [CHANGELOG](CHANGELOG.md).

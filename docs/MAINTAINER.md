# Bảo trì bộ workflow

## Phạm vi bản 0.2.0

Bản đầu dành cho Windows và video đã quay sẵn. Có skill điều phối, snapshot video-use, wrapper nạp key, công cụ Zernio REST độc lập và tài liệu DOCX. Bản 0.2.0 thêm snapshot motion-broll và bridge Windows cho bước minh họa động tùy chọn sau khi edit. Công cụ publishing được tách và điều chỉnh từ AI Video Pipeline; không cần sao chép monorepo.

Publisher đã được build khi chuẩn bị bàn giao. Chưa chạy toàn bộ quy trình trên máy đồng nghiệp sạch, chưa xác minh API key mới và chưa đăng thử qua công cụ đã tách. Người bảo trì nên yêu cầu kiểm tra onboarding và một video mẫu trước khi coi đây là bản ổn định. Không dùng video hoặc tài khoản thật để kiểm tra nếu chưa được chủ tài khoản cho phép.

## Cấu trúc phiên bản

`skills.lock.json` lưu kitFormat, repo nguồn, phiên bản riêng, đường dẫn và SHA256 của từng thành phần. Digest dùng thứ tự đường dẫn POSIX và nội dung file, bỏ qua các thư mục sinh ra khi chạy. `video-use` lưu thêm commit upstream và patch đi kèm.

- `video-use`: snapshot toàn bộ repo upstream, file Python requirements và patch.
- `publisher`: skill social-publishing, mã Node/TypeScript, package-lock và template cấu hình đăng.
- `workflow`: skill điều phối và template môi trường.
- `motion-broll`: skill tích hợp, snapshot upstream tại `tools/vendor/motion-broll` và bridge `tools/motion_broll.py`. Playwright/Chromium cài vào từng project khi cần, không vào source kit.

Thêm thành phần mới cần phát hành **toàn bộ kit** cho người đang dùng bản cũ; updater từng thành phần chỉ hoạt động khi lock hiện tại đã có cùng đường dẫn thành phần. Khi nâng cấp motion-broll upstream, pin commit, kiểm tra giấy phép và API engine, copy snapshot sạch, áp dụng các patch `patches/motion-broll-windows-*.patch` nếu upstream chưa sửa, chạy kiểm tra timeline/attach rồi cập nhật digest. Không chạy `setup.sh` Bash của upstream trên Windows; dùng bridge của kit.

Các script setup, updater, tài liệu và AGENTS.md thuộc phiên bản bộ kit. Khi thay đổi chúng, phát hành cả bộ; cập nhật riêng một skill không thay thế các file chung. Có thay đổi kitFormat phải thực hiện nâng cấp toàn bộ có hướng dẫn di chuyển dữ liệu.

## Nâng cấp video-use từ upstream

1. Làm việc trên branch mới hoặc folder bảo trì riêng; không thay vendor giữa một phiên edit đang chạy.
2. Clone/fetch repo `https://github.com/browser-use/video-use.git` vào thư mục tạm. Chọn commit/tag cụ thể, đọc diff SKILL.md, helpers và pyproject; không mặc định main mới nhất là tương thích.
3. Xuất toàn bộ tracked source vào `.agents/skills/video-use`. Không sao chép `.git`, `.env`, media, cache hoặc môi trường máy tác giả. Giữ LICENSE upstream.
4. Áp dụng `patches/video-use-windows-subtitles.patch` nếu upstream chưa sửa. Nếu upstream thay logic, xử lý lại bản sửa và cập nhật patch; không bỏ qua khi patch thất bại. Không áp dụng patch lần nữa lên snapshot đã sửa.
5. Cập nhật dependencies và pin trong `config/python-requirements.txt`. Bản hiện tại khóa trực tiếp năm dependency chính; dependency bắc cầu do pip giải quyết, vì vậy chưa phải môi trường Python tái tạo tuyệt đối. Ghi lại thay đổi nếu cần chuyển sang uv.lock có kiểm soát.
6. Cập nhật upstreamCommit, version và digest bằng `python tools/lock_components.py --component video-use --version <nhan-phien-ban> --upstream-commit <full-sha>`.
7. Khi đã được yêu cầu kiểm tra, dùng một video mẫu được phép sử dụng: phiên âm có timestamp từng từ, cắt có tiếng, phụ đề tiếng Việt trên Windows, thêm nhạc khi cần và MP4 được publisher nhận. Kiểm tra cấu hình mới bằng `doctor`; kiểm tra local không chứng minh API hoạt động.
8. Ghi kết quả và giới hạn vào CHANGELOG. Nếu chưa kiểm tra đầy đủ thì phát hành prerelease, không gắn nhãn ổn định.
9. Commit, tạo tag bộ kit và ZIP từ tracked source. Người dùng cập nhật thành phần từ tag bộ kit đã duyệt, không từ tag của upstream.

## Xuất ZIP và phát hành

Commit toàn bộ nội dung mong muốn trước, rồi chạy:

```powershell
python tools/manage.py package --output release/video-workflow-kit-v0.1.0.zip
```

Lệnh dùng `git archive HEAD`; không lấy file ignored/untracked. Nó chặn source đang có thay đổi tracked chưa commit. Kiểm tra danh sách file staged trước commit, đặc biệt ảnh mới thêm và tài liệu Word. Không force-add `.env`, `local/` hoặc media. Có thể đưa ZIP lên GitHub Releases và ghi SHA256 trong release notes. Không thêm ZIP vào source Git.

Repo private cần cấp quyền cho đồng nghiệp. Người dùng ZIP không cần GitHub CLI để dùng hàng ngày; cập nhật trực tiếp từ repo private cần Git có quyền đọc repo. Có thể tải ZIP đã được duyệt và dùng `setup/update.ps1 -Component video-use -Source <folder-giai-nen>`.

## Nâng cấp riêng và khôi phục

Updater chỉ thay đường dẫn của thành phần đã chọn, kiểm tra digest hiện tại và bản nguồn, sao lưu dưới `local/backups`, rồi cài dependencies/build lại nếu môi trường đã tồn tại. Nếu dependency build thất bại, nó khôi phục source và cài lại dependencies cũ. Nếu bước khôi phục dependencies cũng lỗi do mạng, dùng lại setup sau khi mạng ổn định. Không cập nhật giữa khi edit, render hoặc publish đang hoạt động.

Các thay đổi trực tiếp vào thành phần sẽ khiến updater dừng để tránh làm mất chỉnh sửa. `.venv`, secrets, media và lịch sử đăng giữ nguyên. Sau cập nhật, lock file trong checkout có thể khác HEAD; đây là trạng thái cục bộ bình thường của việc cập nhật riêng. Người bảo trì cần dùng clone sạch trước khi phát hành.

Rollback khôi phục source phiên bản trước, không đảo ngược bài đã đăng, lịch đã tạo hoặc nội dung video đã dựng. Không dùng cập nhật/rollback để khôi phục một bài đăng mạng xã hội.

## Bổ sung ảnh vào Word

Chụp theo `docs/screenshots/README.md`. Che API key, mã đăng nhập, email cá nhân không cần thiết và thông tin nhạy cảm trước khi lưu ảnh. File `docs/Huong-dan-su-dung.docx` hiện là bản chính, đã chứa nội dung và ảnh bổ sung thủ công. Thay ảnh trực tiếp trong Word bằng Change Picture hoặc sửa tài liệu hiện có bằng python-docx, giữ nguyên các ảnh đã chèn. Lưu bản dự phòng trước khi sửa.

`python tools/build_guide.py` chỉ tạo bản nháp ban đầu ở `local/guide-draft.docx`; không ghi đè tài liệu chính. Nội dung bản nháp không thay thế các chỉnh sửa thủ công mới nhất. Các ảnh thực được lưu riêng trong `docs/screenshots/`; nguồn ảnh nằm ở `SOURCES.md` cùng folder.

Giữ hình ảnh giao diện thực; không dùng ảnh giả để minh họa nơi tạo key. Placeholder hiện tại chỉ ghi rõ nội dung cần chụp. Nếu sửa layout, render và xem lại toàn bộ trang trước khi phát hành. Máy tác giả cần công cụ render DOCX phù hợp; máy người dùng chỉ cần Word hoặc ứng dụng đọc DOCX.

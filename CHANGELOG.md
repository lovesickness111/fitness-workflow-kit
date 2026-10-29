# Changelog

## 0.3.4 (prerelease)

Bản phát hành gộp 0.3.2 và 0.3.3, kèm các chỉnh sửa sau (thành phần `fitness-explainer` 0.12.2):

- Mặc định vẽ ảnh của kênh mới trở lại **Codex**, dự phòng bằng Gemini. API That (`provider: gateway`) là tùy chọn: Claude chỉ chuyển sang khi người dùng có key `IMAGE_GATEWAY_API_KEY` và yêu cầu. Trước khi chuyển, Claude báo rằng ảnh tham chiếu và prompt sẽ được gửi qua dịch vụ trung gian đó. Kênh đã tạo trước đây giữ nguyên lựa chọn cũ.
- Skill ghi rõ: khối `channel.image` thuộc lần duyệt kênh và dấu vân tay ảnh, nên đổi bên vẽ sau khi đã có ảnh sẽ phải vẽ lại toàn bộ (báo chi phí trước).
- Hướng dẫn: `START-HERE.md`, `README.md` và `AGENTS.md` thêm các phần sau, kèm chi phí và lưu ý dữ liệu.
  - API That tùy chọn.
  - Nhạc nền Lyria tạo riêng cho từng video bằng key Gemini.
  - Bộ SFX do người dùng tự tải.
- `2-Nhap-key.cmd` ghi Gemini dùng cho nhạc Lyria, ghi API That là tùy chọn. `config/.env.example` thêm `IMAGE_GATEWAY_API_KEY`.

## 0.3.3 (prerelease)

Fitness (thành phần `fitness-explainer` 0.12.1): vẽ ảnh qua API That.

- Mặc định mới cho kênh: `channel.image.provider = "gateway"`, model `gpt-image-2.5-sunburst`, host `https://api.apithat.dev/v1`, key `IMAGE_GATEWAY_API_KEY` (nhập bằng `2-Nhap-key.cmd`), dự phòng Gemini.
- Host `apithat.dev` được tự đổi sang `api.apithat.dev`. Theo tài liệu API That, host này không qua Cloudflare nên ảnh lâu không bị cắt 524. Đổi trong code nên dấu vân tay ảnh pose và lần duyệt kênh không đổi.
- Timeout client 600 giây. Hết thời gian đọc hoặc HTTP 524 được coi là kết quả không chắc chắn: không tự thử lại, không chuyển sang Gemini, vì ảnh có thể đã bị tính phí. Thiếu key thì báo lỗi ngay, không gửi request.
- `doctor` hiện dòng `IMAGE_GATEWAY_API_KEY` khi có key.
- Kiểm thử: thêm `test_gateway_uses_image_host_and_never_falls_back_after_a_timeout` (giả lập HTTP, không gọi API thật). Chưa tạo ảnh thật bằng `gpt-image-2.5-sunburst`.

## 0.3.2 (prerelease)

Fitness (thành phần `fitness-explainer` 0.12.0): hiệu ứng, SFX và nhạc nền, rút ra từ việc phân tích 25 video kênh tham chiếu và từ các video đã làm.

- Chuyển cảnh:
  - Mặc định là **mờ nhòe 0,22 giây**: cảnh cũ nhòe đi ở 0,14 giây cuối, cảnh mới hiện ra từ nhòe. Thay cho kiểu mờ dần từ đen trước đây.
  - Field mới `transition`: `blur | swipe | impact | cut | fade`, và `impact: true`.
  - `swipe`: cảnh lướt lên từ dưới kèm nhòe chuyển động dọc.
  - `impact`: 3 khung trắng âm bản có tia tốc độ manga, sau đó zoom nhòe vào cảnh.
  - Cảnh trước chỉ nhòe ra khi cảnh sau vào bằng nhòe, nên cú cắt vào impact hay swipe vẫn sắc.
  - Đặt mặc định cho cả kênh bằng `channel.motion.transition`, cho từng video bằng `brief.transition`.
- Từ khóa (`accent`) **phát sáng neon** theo màu của nó. Lúc xuất hiện, lõi chữ bừng gần trắng khoảng 0,1 giây rồi lắng xuống và "thở". Tắt bằng `channel.motion.keyword_glow: false`.
- Bốn component mới:
  - `holdbar`: đồng hồ tự kiểm tra, 10 ô mỗi ô một giây, có trạng thái hỏng "Touch = stop".
  - `angle`: chữ L neon có chân xoay tới góc.
  - `switch`: công tắc dễ/khó.
  - `dose`: chip đồng hồ bấm giờ "20–30s × 3" với chấm hiệp.
- SFX tự động:
  - `channel sfx-pack --source <thư mục>` dựng 11 âm (cắt, fade, cân âm lượng) từ bộ SFX của chính người dùng. Mặc định khớp bộ Mister Horse miễn phí; đổi từng âm bằng `--map`.
  - `build` tạo `audio/sfx.wav` từ chính cấu hình cảnh: chuyển cảnh, tiêu đề, chữ, badge, đồng hồ, dấu ✕/✓, cảnh báo, panel và các component mới. Mỗi 0,12 giây chỉ giữ một âm, sự kiện lớn thắng. Danh sách âm ghi ở `audio/sfx.json`.
  - `check` đo đỉnh SFX và nhắc khi SFX to hơn -6 dBFS.
- Nhạc nền mới cho từng video:
  - Cấu hình `channel.music = {"provider": "lyria", "gain_db": -18, "duck": false}`, phong cách đặt trong `brief.music`, chạy lệnh `music`.
  - Nhạc được tạo đủ độ dài video (không lặp), fade, chuẩn -16 LUFS. Bản nào có đoạn im lặng (stream bị đứt) sẽ bị từ chối.
  - `local/fitness/music_log.json` lưu các phong cách đã dùng; dùng lại phải thêm `--allow-repeat`.
  - `duck: false` trộn nhạc không nén. Phần mô tả khi đăng ghi nguồn "made with Google Lyria".
  - Thêm `google-genai==2.33.0` vào `config/fitness/requirements.txt`. Phần code phiên Lyria theo `lyria-recipe.py` của HyperFrames media-use (Apache 2.0).
- Style guide:
  - Nhịp dựng theo kênh tham chiếu: phút đầu 15–25 lần đổi, thân bài 3–7 giây mỗi tư thế.
  - Quy tắc prompt: ghi rõ điểm tiếp xúc; phía trước chân đang giữ không có vật gì; prompt cận cảnh hay ra cả người lơ lửng.
  - Danh sách kiểm tra ảnh: không lơ lửng, chân không gác lên đạo cụ, đạo cụ giữ màu xám, so từng ảnh với câu thoại của nó.
- Sửa chỉ số input của SFX trong `assemble` khi nhạc không lặp. Hồ sơ kênh chỉ đưa `sfx`/`motion` vào digest khi được cấu hình, nên kênh đã duyệt trước đây không bị mất duyệt.
- Kiểm thử: thêm `test_transitions_glow_and_hud_panels_render`, gồm render khung hình thật, dựng pack SFX giả, trộn SFX + nhạc và giả lập Lyria. 28/28 test đạt. Lyria thật và một video đầy đủ trên máy sạch chưa được chạy.

## 0.3.1 (prerelease)

- Fitness: tag ở góc trên bên trái giờ đổi theo từng ý chính của video, giống heading trong văn bản.
  - `brief.tag` là heading mở đầu. Cảnh đầu tiên của mỗi ý mới ghi `"tag": "<heading mới>"`, và heading đó giữ nguyên cho các cảnh sau tới khi có cảnh khác đổi. `"tag": false` vẫn chỉ ẩn ở đúng cảnh đó.
  - Ở cảnh đổi heading, dòng cũ trượt lên và mờ đi, dòng mới trượt vào trong khoảng 0,5 giây. Trong cùng một ý, heading đứng yên.
  - Bước duyệt nội dung in danh sách heading và cảnh bắt đầu của mỗi heading.
  - `notes` lấy các heading làm chương YouTube, bỏ phần chung của mọi heading (ví dụ "Grip"). Nếu chưa đủ 3 chương cách nhau ít nhất 10 giây thì quay về cách chia theo nhóm segment như trước.
  - Video chỉ có một tag, như tendon-holds, vẫn hiển thị như cũ.

## 0.3.0 (prerelease)

- Bàn giao cho Claude Desktop:
  - `CLAUDE.md` nạp `AGENTS.md`, kèm quy tắc cho người dùng không rành kỹ thuật và quy tắc giữ key.
  - Mỗi skill có file trỏ trong `.claude/skills/`, để Claude Code tìm thấy; bản chính vẫn nằm ở `.agents/skills/`.
  - Viết lại `START-HERE.md` và `README.md` theo luồng: tải ZIP, bấm đúp 4 file, mở thư mục trong Claude Desktop.
- Sửa lỗi trên máy sạch: phần render fitness giờ cài bên trong `setup.ps1`, sau khi đã nạp lại PATH. Trước đây `1-Cai-dat.cmd` chạy bước này với PATH cũ nên báo thiếu Node/FFmpeg ngay sau khi winget vừa cài. Launcher dừng và báo rõ khi cài lỗi.
- Sửa lỗi khóa thành phần trên máy khách. Digest trong `skills.lock.json` trước đây tính cả kiểu xuống dòng, nên bản ZIP/clone (LF) lệch với bản soạn trên Windows (CRLF). Hệ quả: `3-Kiem-tra.cmd` báo ACTION ở mọi thành phần và lệnh cập nhật từ chối chạy. Giờ digest bỏ qua CRLF/LF với file văn bản, và `manage.py package` kiểm tra lại digest ngay trong ZIP trước khi xuất.
- `.gitattributes` giữ CRLF cho file `.cmd` và không đưa `docs/plans/` (ghi chú nội bộ) vào ZIP. `.gitignore` bỏ qua `*.pending` và `.claude/settings.local.json`. `config/.env.example` có thêm `GENMAX_API_KEY` và `GEMINI_API_KEY`.
- Thêm workflow `fitness-explainer`: tạo trọn video giải thích fitness tiếng Anh theo phong cách manga nền đen.
  - Giọng đọc Genmax, ưu tiên hơn Gemini TTS. Tư thế nhân vật sinh bằng Gemini từ ảnh tham chiếu đã duyệt.
  - Hậu xử lý ảnh: ép nền về #000, tô quần đúng màu nhận diện.
  - Bộ mẫu cảnh HTML (zoom chậm, rung, gân đỏ nhấp nháy, đồng hồ, biểu đồ có nguồn, nhãn, hộp cảnh báo, chữ chạy theo cụm) cho 9:16 và 16:9.
  - Ba lần duyệt gắn digest; lưu task Genmax và đối chiếu khi submit không rõ kết quả.
  - Bản preview nén dùng cùng nhịp với bản cuối.
  - Kiểm thử offline có render thật.
- Fitness: hỗ trợ nhiều nhân vật trong một kênh.
  - Mỗi nhân vật có nhiều ảnh tham chiếu và một màu nhận diện riêng, hoặc để trắng đen hoàn toàn.
  - Lệnh `channel add-reference` nhập ảnh của người dùng và tự cắt theo nhân vật.
  - Mỗi tư thế có thể có một hoặc nhiều nhân vật.
  - Tô lại màu theo hue của từng màu nhận diện (ví dụ quần xanh), không còn cố định màu cam.
  - Nhạc nền có license khai báo trong hồ sơ kênh; mặc định −16 dB, ép nhẹ (nhạc thấp hơn giọng khoảng 22 LU, thay vì 31 LU như trước). `channel.music.duck` chỉnh được độ ép.
- Fitness: tối ưu sau video thử.
  - Lệnh mới: `produce` và `build` gộp các bước; `storyboard` tạo một ảnh xem toàn clip; `check` đo LUFS, đỉnh và mức nhạc, kèm bảng khung hình; `research` tra DOI trên Crossref.
  - Duyệt không cần chép tay digest.
  - Bảng ảnh tư thế có lưới tọa độ để đặt vị trí gân đỏ.
  - Render cảnh và tạo tư thế song song (`--jobs`).
  - `status` báo credit Genmax và số ảnh Gemini đã dùng.
  - Kênh có nhiều giọng preset, mỗi video chọn được giọng riêng (giọng thuộc lần duyệt media).
  - Mép ảnh tư thế mờ dần vào nền đen.
  - Khung 9:16: hạ khung nhân vật 2,5% để chữ chạy 2 dòng không chạm đầu.
- Fitness: chế độ chạy theo lô cho Gemini (`image.batch: true` khi `provider: gemini`).
  - Lượt vẽ đầu của cả bộ tư thế gửi trong 1 job Batch API, rẻ hơn 50%.
  - Mã job được lưu trước khi chờ; chạy lại chỉ hỏi job cũ; dùng `--reconcile-batch` khi không rõ lô đã gửi chưa.
  - Ảnh lỗi trong lô được vẽ lại riêng bằng cách thường và có ghi lý do.
  - Ảnh tham chiếu thu nhỏ còn 768px JPEG cho vừa giới hạn 20 MB.
  - Đã đối chiếu với API thật.
- Fitness: dòng tiêu đề ghim ở góc trên bên trái (`brief.tag`), có vạch đỏ, chữ in hoa nhỏ, hiện cố định ở mọi cảnh. Ô nhãn tự dời xuống dưới tag; ở 9:16 dải chữ và bảng biểu đồ cũng dời theo. Cảnh nào không muốn hiện thì đặt `"tag": false`. Đặt tag ngay khi tạo bằng `init --tag`; bản duyệt nội dung luôn hiện dòng tag, hoặc báo MISSING nếu chưa có.
- Đóng gói skill `codex-image` vào kit (thành phần `codex-image` 1.0.0, bản chính ở `.agents/skills/codex-image`, `.claude` chỉ còn file trỏ tới).
  - `setup.ps1` cài Codex CLI qua winget nếu thiếu; lỗi cài chỉ cảnh báo, vì đã có Gemini dự phòng.
  - File bấm đúp `4-Dang-nhap-Codex.cmd` để đăng nhập bằng tài khoản ChatGPT của chính khách.
  - `doctor` báo trạng thái đăng nhập Codex.
  - Script đọc `CODEX_BIN` khi chỉ có bản cài npm.
- Fitness: ảnh sinh bằng Codex (skill codex-image, gói ChatGPT) làm nguồn chính, Gemini làm dự phòng khi Codex lỗi (`channel.image.provider` / `fallback`).
  - Hồ sơ mỗi ảnh ghi rõ bên đã vẽ và lý do chuyển sang dự phòng; khung 3:4, 4:3, 16:9 được cắt từ khung gần nhất mà Codex hỗ trợ.
  - Prompt tư thế giờ yêu cầu vẽ đủ đạo cụ được nhắc tới (tường, bậc thang, khung cửa, xà, khăn).
- Fitness: thêm mẫu minh họa theo những gì video tham khảo dùng: `split` (so sánh 2 khung), `plan` (hàng hình tư thế), `table` (bảng phân mức hoặc các bước), `meter` (thanh gắng sức), `inset` (ảnh cận giải phẫu có gân đỏ), `labels` và `marks` (nhãn chú thích, dấu X, dấu ✓, mũi tên).
  - Loại ảnh `illustration` (hình ẩn dụ, giải phẫu, đồ vật không có nhân vật) giữ được một màu nhấn.
  - Số liệu trong khung so sánh bắt buộc có `claim_id`.
- Fitness: chế độ tham khảo video có sẵn.
  - `reference --url` lấy thông tin, chương, mô tả và phụ đề YouTube (không tải video), chịu được lỗi 429 khi tải phụ đề.
  - `reference --video` chụp khung hình theo cảnh từ file người dùng tự tải; `--describe` nhờ Gemini mô tả bố cục và HUD từng khung.
  - `--subs` / `--transcribe` (Genmax speech-to-text) khi không có phụ đề.
  - Khung minh họa lấy từ storyboard YouTube, không cần tải video; lọc bỏ khung đen, chuyển cảnh và khung trùng (so cả màu), chấm điểm theo mức có đồ họa.
  - `skeleton` gắn các khung minh họa tiêu biểu vào từng chương và xuất ảnh `skeleton-<s>s.png` (kèm nhãn mẫu cảnh nếu đã chạy `--describe`).
  - Gợi ý nghiên cứu được trích dẫn qua Europe PMC.
  - `skeleton` thu nhỏ cấu trúc theo thời lượng mục tiêu; `originality` đo câu trùng lời với video gốc, hiện trong bước duyệt nội dung.
  - `notes` soạn nháp mô tả khi đăng (chương, nghiên cứu, an toàn, ghi nguồn nhạc).
  - Thêm `config/fitness/requirements.txt` (yt-dlp), cài khi chạy `fitness_video.py setup`.
- Cập nhật file khóa motion-broll (`3d83d98-kit.4`) theo hướng dẫn đã sửa; `doctor` không còn báo lệch.
- `setup/configure.ps1` nhập ẩn thêm `GEMINI_API_KEY` và `GENMAX_API_KEY`.
  - Mỗi key có hướng dẫn tiếng Việt và cho biết key nào đã lưu.
  - Thêm các file bấm đúp `1-Cai-dat.cmd`, `2-Nhap-key.cmd`, `3-Kiem-tra.cmd` cho người dùng không rành kỹ thuật.
  - `setup.ps1 -NoDoctor` bỏ bước kiểm tra cuối khi chạy từ launcher.
- Sửa kiểm tra phiên bản Node trong `setup/setup.ps1`. Trên Windows PowerShell 5.1, dấu nháy kép trong tham số bị mất nên setup luôn báo thiếu Node 22+.
- Bổ sung luồng hoàn thiện clip dọc 3:4/9:16 đã có karaoke: phân biệt caption dính hình với subtitle track, cắt hình/tiếng cùng nhau trước motion, giữ vùng caption bằng panel alpha và kiểm tra highlight sau mỗi điểm cắt. Ghi rõ giới hạn resize và preview dọc của helper hiện tại.
- Cập nhật skill workflow theo phiên dựng thực tế: tiếp tục từ checkpoint, tái dùng transcript/phụ đề đã sửa, giữ khung hình nguồn và ghi rõ file được duyệt.
- Thêm hướng dẫn phân biệt timestamp nguồn, bản cắt và bản tăng tốc; hoàn thiện tốc độ trên video/âm thanh đã composite, không thêm trường speed không được hỗ trợ vào EDL.
- Sửa hướng dẫn motion để giữ phụ đề ASS/SRT đã biên tập và kiểm tra bản xuất sau tăng tốc, kể cả bài giảng khung 16:10.
- Cập nhật skill publishing: chốt bản nháp title/caption trước upload, cấu hình nhiều profile, giữ session ID của CLI và báo kết quả từng nền tảng khi có timeout. Không thay đổi cơ chế tạo/retry bài đăng.

## 0.2.0

- Thêm motion-broll (upstream commit 3d83d98) như bước minh họa động tùy chọn sau khi chốt cut video-use và trước khi đăng.
- Bridge Windows tái dùng transcript từng từ, chuyển timestamp qua các đoạn cắt, kiểm tra clip render và tạo `edit/edl.motion.json` mà không ghi đè EDL gốc.
- Bản motion xuất riêng `edit/final-motion.mp4`; vẫn cần duyệt kế hoạch cảnh và xem toàn bộ bản render cuối trước khi đăng.
- Chưa kiểm thử end-to-end trên video thật hoặc máy Windows sạch; tiếp tục xem là prerelease.

## 0.1.1

- Hoàn thiện hướng dẫn đăng ký ElevenLabs và Zernio, quyền Speech to Text, key Read & Write và phạm vi profile.
- Giữ nguyên năm ảnh người dùng chèn thủ công; bổ sung ảnh trang đăng ký và ảnh từ tài liệu chính thức, kèm nguồn.
- Cập nhật hướng dẫn tải repo public và dàn trang Word.
- File DOCX là bản chính; công cụ tạo bản nháp không còn ghi đè tài liệu đã chỉnh thủ công.
- Không thay đổi mã publisher, vendor video-use hoặc cấu hình credential.

## 0.1.0

- First handoff package for Windows with project-local skills.
- Bundled video-use commit 43cfc56 and Windows subtitle path patch.
- Standalone Zernio publisher for selected platforms and one or more credential profiles.
- Existing-video import, preparation review, persistent attempts, account reconciliation and run locking.
- Masked key input, isolated Python setup, component updater/rollback and source-only ZIP packaging.
- Vietnamese Word guide with clearly labeled screenshot positions and replaceable PNG assets.
- Publisher build completed. End-to-end onboarding on a clean colleague machine and live API/publish verification remain to be requested and performed. Initial release is a prerelease.

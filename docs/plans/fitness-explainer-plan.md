# Kế hoạch: workflow Fitness Explainer

Trạng thái (2026-10-25):
- **Đã duyệt; MVP đã triển khai.** Gồm `tools/fitness_video.py`, `tools/fitness/` và skill `.agents/skills/fitness-explainer`.
- Kiểm thử offline đều qua, kể cả render thật cả hai khung hình với provider giả lập.
- Chưa gọi Genmax/Gemini thật vì máy chưa có key.
- Mặc định đã chọn khi chưa có câu trả lời: giữ các tính năng cũ của kit, MVP chưa có nhạc, quần cam (đổi được trong `local/fitness/channel.json`), video thử "Wall Hold" 9:16.

## Mục tiêu

Từ một chủ đề tập luyện, tạo trọn một video giải thích tiếng Anh theo phong cách:

- nền đen #000;
- nhân vật cơ bắp vẽ kiểu manga trắng đen, quần màu nhận diện;
- gân/cơ phát sáng đỏ khi chịu lực;
- HUD xanh lá: đồng hồ đếm giây, biểu đồ;
- nhãn phân đoạn, hộp cảnh báo an toàn, chữ chạy theo cụm.

Video ở khung 9:16 hoặc 16:9, dừng ở mỗi bước quan trọng để người dùng duyệt, đăng bằng publisher Zernio đã có trong kit.

Workflow độc lập, không import hay dùng chung code với `ai-video-pipeline`. Các ý tưởng đã kiểm chứng ở agent-video được viết lại gọn cho repo này: duyệt theo digest, checkpoint, không gửi lại yêu cầu có kết quả chưa rõ.

## Quyết định đã chốt

| Mục | Quyết định |
|---|---|
| Giọng đọc | Tiếng Anh mặc định, qua Genmax API (`GENMAX_API_KEY`) |
| Ảnh | Gemini API (`GEMINI_API_KEY`), có ảnh tham chiếu để giữ nhân vật đồng nhất |
| Khung hình | Chọn 9:16 hoặc 16:9 khi khởi tạo mỗi video |
| Duyệt | Dừng ở từng bước quan trọng |
| Chữ chạy | Theo câu/cụm (v1); chạy từng từ để sau |
| Bộ mẫu cảnh | Làm bộ component dùng chung theo đề xuất |

## Luồng chính

```text
init (chọn khung, kênh)
  -> research + claims -> script -> storyboard          ⏸ Duyệt 1: Nội dung
  -> audio (Genmax) + poses (Gemini) + hậu xử lý ảnh     ⏸ Duyệt 2: Media (nghe giọng, xem ảnh)
  -> visuals (render từng cảnh) -> preview MP4 nén       ⏸ Duyệt 3: Bản dựng
  -> render final.mp4 + delivery.json
  -> social-publishing (Zernio)                          ⏸ Duyệt đăng: kế hoạch đăng cụ thể
```

Một lần cho mỗi kênh, trước video đầu tiên: **⏸ Duyệt kênh**, gồm chọn giọng từ mẫu nghe thử và chọn ảnh tham chiếu nhân vật.

## Cấu trúc

Repo (thêm mới):

```text
.agents/skills/fitness-explainer/
  SKILL.md                      quy trình, gates, quy tắc nội dung/an toàn
  references/style-guide.md     bảng màu, font, bố cục 9:16/16:9, prompt nhân vật
  references/scene-templates.md tham số từng mẫu cảnh
tools/fitness_video.py          CLI: init/status/review/approve/voices/audio/poses/visuals/preview/render
tools/fitness/                  module: state, genmax, gemini_image, imaging, timing, assemble
tools/fitness/templates/        HTML/JS mẫu cảnh + fonts (OFL) + runtime seek(t)
config/fitness/channel.example.json
tests/test_fitness_*.py         kiểm thử offline (provider giả lập)
```

Hồ sơ kênh thật nằm trong `local/fitness/` (bị ignore), gồm: `channel.json`, ảnh tham chiếu nhân vật, mẫu giọng đã chọn.

Mỗi video:

```text
projects/<video>/
  brief.json          chủ đề, người xem, khung hình, độ dài mong muốn
  research/           sources.json, claims.json (nguồn cho mọi con số/khẳng định)
  script.json         segments: id, text, delivery
  storyboard.json     mỗi cảnh: template, pose, HUD, từ khóa tô màu
  assets/poses/       raw/ (Gemini) -> <pose>.png đã chuẩn hóa
  audio/              <segment>.wav + tasks.json (task ID Genmax)
  render/             scenes/, preview.mp4, final.mp4, delivery.json
  state.json          approvals, cache fingerprint, QA (do CLI quản lý)
```

## Chi tiết

### 1. Hồ sơ kênh

`channel.json` gồm:

- bảng màu (base #000, white, signature, highlight red, accent green, warning yellow);
- font (Montserrat Black/Poppins Bold);
- `voice`: provider, voice_id, model_id, language_code, voice_settings;
- đường dẫn ảnh tham chiếu nhân vật, mô tả nhân vật cố định, fps mặc định;
- nhạc nền tùy chọn (chỉ file có license).

Không dùng nhân vật, màu hay branding của kênh mẫu. Màu quần là màu nhận diện của kênh, sẽ chốt ở Duyệt kênh.

### 2. Nội dung

- Research ghi nguồn có id và vị trí trích dẫn. `claims.json` liệt kê từng khẳng định kèm nguồn.
- **Mọi con số trên biểu đồ phải gắn `claim_id`.** Không bịa số liệu sức khỏe. Không có nguồn thì không dùng biểu đồ số liệu.
- Bài tập có rủi ro (khớp, gân, huyết áp) phải có cảnh cảnh báo an toàn. Không đưa lời khuyên y khoa.
- Script tiếng Anh, chỉ `segments[].text` được đọc; hướng dẫn giọng để ở `delivery`.
- Ở Duyệt 1, trình **toàn bộ script và hướng minh họa của từng cảnh**, không chỉ tóm tắt.

### 3. Giọng Genmax

Theo tài liệu công khai tại genmax.io/docs:

- Header `xi-api-key`.
- `POST /v1/text-to-speech/{voice_id}` trả về 202 kèm `id`. Sau đó gọi `GET /v1/history/{id}` để lấy `result.audio_url` (mp3).
- Provider elevenlabs/minimax/capcut; bắt buộc `language_code`.

Thiết kế:

- `voices`: liệt kê giọng tiếng Anh. `voices --sample`: tạo 3–4 câu mẫu (tốn credit, hỏi trước) để chọn ở Duyệt kênh.
- `audio`: mỗi segment một request.
  - Ghi task ID vào `audio/tasks.json` **ngay khi nhận**, rồi mới poll.
  - Bị ngắt thì poll tiếp theo ID cũ.
  - Submit không rõ kết quả (timeout, không có ID) thì kiểm tra history trước, **không gửi lại**.
- Tải mp3, chuyển sang WAV 48 kHz, đo thời lượng thật. Cache theo text + voice + model + settings, nên sửa một cảnh chỉ tạo lại cảnh đó.
- Không log key hay URL có token.

### 4. Ảnh nhân vật (Gemini)

1. **Duyệt kênh:** tạo 3–4 phương án nhân vật đứng thẳng, mặt trước, nền đen. Người dùng chọn một làm `reference.png`.
2. **Từng tư thế:** prompt chuẩn (style guide) + ảnh tham chiếu → ảnh tư thế (wall sit, hang, calf raise…), khung theo tỷ lệ video. Quần vẽ màu cam phẳng để dễ tách.
3. **Hậu xử lý tự động** (`imaging`):
   - Ép vùng gần đen về đúng #000 để không lộ viền khung ảnh.
   - Đưa phần còn lại về trắng đen.
   - Tách vùng quần theo dải màu và tô lại đúng mã màu nhận diện, giữ sắc độ.
4. **Gân đỏ không vẽ vào ảnh.** Đây là lớp SVG/CSS glow riêng, toạ độ chuẩn hóa theo ảnh tư thế, khai báo trong storyboard, để nhấp nháy độc lập.
5. Contact sheet tất cả tư thế, kèm lớp gân đỏ chồng lên, cho Duyệt 2.

Nền canvas đã đen nên không cần tách nền. Chỉ khi có lớp nằm sau nhân vật mới dùng `mix-blend-mode: lighten`.

### 5. Bộ mẫu cảnh

Mỗi mẫu là hàm thuần của `t`: không timer, không trạng thái. Render bằng `tools/vendor/motion-broll/engine/render.js` hiện có, theo contract: `#stage`, `window.DURATION`, `seek(t)`; không sửa vendor.

| Mẫu | Nội dung |
|---|---|
| `pose-stage` | Ảnh tư thế + Ken Burns 1.0→1.08 về điểm nhấn + rung nhẹ khi gồng + lớp gân đỏ pulse |
| `timer-ring` | Vòng tròn xanh lá chạy 0→100%, số giây nhảy |
| `bar-compare` | Thanh ngang trượt ra (ease-out) + % (bắt buộc claim_id) |
| `badge` | Nhãn góc trên trái: "HOLD 1 • THE WALL HOLD" |
| `warning-box` | Hộp lưu ý an toàn màu vàng |
| `kinetic-text` | Chữ theo cụm, từ khóa tô trắng/cam/đỏ |
| `title-card`, `outro` | Mở/kết |

- Một cảnh là một `pose-stage` cộng các component HUD, mỗi component có thời điểm vào/ra.
- Thời điểm lấy theo ranh giới câu trong audio thật, đo bằng `ffmpeg silencedetect`. Không gọi API, không chia đều.
- Có bố cục riêng cho 16:9 và 9:16. Bố cục 9:16 chừa vùng an toàn cho UI của TikTok/Shorts.

### 6. Dựng và xuất

- `visuals`: render từng cảnh đúng thời lượng audio của cảnh, cache theo fingerprint (HTML, ảnh, audio, khung).
- `preview`: ghép cảnh + giọng (+ nhạc nếu có), xuất MP4 nén (720p, dưới 50 MB) để gửi Telegram nghe/xem. Timing và mix giống bản cuối.
- `render`: chỉ chạy sau Duyệt 3. Xuất `final.mp4` (H.264/AAC, −14 LUFS) và `delivery.json` (SHA-256 file, digest các lần duyệt, đầu vào).

### 7. Duyệt và state

- `review --gate X` in digest của đúng nội dung đang trình. `approve --gate X --expected-sha256 … --decision "<câu trả lời thật của người dùng>"`.
- Agent không tự duyệt và không coi im lặng là đồng ý.
- Sửa nội dung thì các lần duyệt sau thành stale. Đổi media thì Duyệt 2–3 stale.
- Agent không nghe được audio: chỉ ghi "đã nghe" khi người dùng phản hồi sau khi nghe bản preview.

### 8. Đăng

Dùng `social-publishing` và publisher hiện có với `final.mp4`. Trình caption, tài khoản, quyền riêng tư và thời điểm, rồi chỉ đăng khi có duyệt cụ thể. Run cũ được tiếp tục, không tạo run mới.

## Kiểm thử

Kiểm thử offline, không gọi API thật:

- Genmax giả lập: submit, poll, timeout, task chưa rõ (không resubmit).
- Gemini giả lập: ảnh mẫu.
- Hậu xử lý ảnh: ép #000, tô màu quần.
- Render từng mẫu cảnh ở cả 9:16 và 16:9, kích thước nhỏ.
- Gates/digest bị stale khi đổi nội dung.
- Ghép preview/final đúng thời lượng.

Chạy theo kiểu `tests/test_motion_broll.py` (unittest).

## Lộ trình

1. **MVP:**
   - CLI + state + gates.
   - Genmax audio.
   - Ảnh tham chiếu + 2–3 tư thế + hậu xử lý.
   - Các mẫu `pose-stage`, `timer-ring`, `badge`, `warning-box`, `kinetic-text`.
   - Một video thử khoảng 45 s, 9:16, chủ đề "Wall Hold", chạy qua đủ các gate.
2. **Hoàn thiện:**
   - `bar-compare`, `title-card`/`outro`, bố cục 16:9.
   - Nhạc nền có license.
   - Tài liệu `START-HERE`, `AGENTS.md`, `skills.lock.json`, CHANGELOG.
3. **Sau:**
   - Chữ chạy từng từ (Whisper chạy trên máy).
   - Thêm mẫu cảnh.

## Rủi ro / cần kiểm chứng khi làm

- Máy này chưa có `.venv` của kit: cần chạy `setup/setup.ps1` trước khi chạy/kiểm thử.
- Chưa xác minh với key thật:
  - base URL Genmax (`https://api.genmax.io` theo ví dụ của bạn), endpoint liệt kê giọng, định dạng mp3 trả về;
  - cách gửi ảnh tham chiếu cho model ảnh Gemini.
  - Mỗi thứ sẽ thử bằng **một** request nhỏ, có báo trước chi phí.
- Gemini không bảo đảm nhân vật giống hệt 100% giữa các tư thế. Ảnh lệch thì tạo lại riêng ảnh đó ở Duyệt 2.
- Quyền dùng giọng cho video kiếm tiền phụ thuộc điều khoản của Genmax và provider gốc. Nên kiểm tra trước khi đăng công khai.
- Chi phí credit Genmax/Gemini: CLI sẽ báo số ký tự/số ảnh trước khi tạo hàng loạt.

## Câu hỏi còn mở

1. Giữ các tính năng cũ của kit (dựng video có sẵn bằng video-use, B-roll) song song, hay bỏ để repo chỉ còn fitness? Mặc định: giữ.
2. Nhạc nền cho MVP: không dùng, hay bạn có file nhạc có license?
3. Màu nhận diện của nhân vật: giữ cam, hay chọn màu riêng?
4. Chủ đề video thử: "Wall Hold", 9:16, khoảng 45 s, có được không?

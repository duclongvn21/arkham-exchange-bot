# Arkham Exchange Flow Monitor

Ứng dụng theo dõi **toàn bộ token trên Arkham**, phát hiện dòng tiền chuyển
lên sàn (inflow — có thể sắp bị bán) hoặc rút khỏi sàn (outflow — tín hiệu
tích lũy) **đột biến**. Có 2 cách dùng:

- **Web app** (`app.py`) — dashboard trên trình duyệt, chỉnh ngưỡng cảnh báo
  trực tiếp trên web, xem lịch sử cảnh báo dạng bảng, tự động refresh.
- **CLI** (`bot.py`) — chạy nền đơn giản, không cần trình duyệt.

Cả 2 đều dùng chung logic ở `arkham_core.py` và đều gửi được cảnh báo qua
Telegram.

## 1. Cài đặt

```bash
cd arkham-exchange-bot
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Dán API key Arkham của bạn vào `ARKHAM_API_KEY` trong file `.env`.

## 2. (Tùy chọn) Tạo Telegram Bot để nhận cảnh báo qua điện thoại

1. Mở Telegram, tìm **@BotFather**, gửi lệnh `/newbot`, đặt tên tùy ý.
2. BotFather trả về 1 chuỗi token dạng `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`
   → dán vào `TELEGRAM_BOT_TOKEN` trong `.env`.
3. Mở chat với bot vừa tạo, bấm **Start**.
4. Lấy Chat ID của bạn: tìm **@userinfobot** trên Telegram, gửi `/start`,
   nó trả về ID dạng số → dán vào `TELEGRAM_CHAT_ID`.

Nếu bỏ qua bước này, cảnh báo vẫn hiển thị đầy đủ trên dashboard web,
chỉ là không được đẩy qua điện thoại.

## 3. Chạy thử — kiểm tra dữ liệu API (bắt buộc lần đầu)

```bash
python bot.py --debug --once
```

Lệnh này in ra JSON gốc mà Arkham trả về. Mở file `arkham_core.py`, tìm hàm
`parse_token_row()`, đối chiếu tên field trong JSON in ra với các dòng
`row.get("symbol")`, `row.get("inflowCex")`, `row.get("marketCap")`...
— nếu Arkham đặt tên khác, sửa lại cho khớp (chỉ 1 hàm này). Tài liệu API
chi tiết của Arkham không truy cập tự động được lúc viết app này nên tên
field được suy ra từ tài liệu cộng đồng, có thể lệch nhẹ.

## 4A. Chạy Web App (khuyến nghị)

```bash
python app.py
```

Mở trình duyệt tại **http://localhost:5000**

- **Dashboard**: bảng cảnh báo real-time (tự refresh mỗi 10s), lọc theo
  chiều Vào sàn/Ra sàn, nút "Quét ngay" để kiểm tra tức thì thay vì đợi
  chu kỳ, banner báo lỗi nếu API key sai/hết hạn.
- **Cài đặt**: đổi ngưỡng USD, tỷ lệ % market cap, khung giờ, tần suất quét,
  cooldown chống spam — lưu ngay lập tức, không cần khởi động lại app
  (tự động ghi lại vào `.env` để giữ cấu hình sau khi restart).

Để chạy 24/7 trên server, dùng WSGI server thật thay vì dev server:

```bash
pip install gunicorn
gunicorn -w 1 -b 0.0.0.0:5000 app:app
```

> Lưu ý: chỉ chạy **1 worker** (`-w 1`) vì vòng quét nền (background thread)
> chạy trong tiến trình app — nhiều worker sẽ tạo nhiều vòng quét trùng nhau.

Muốn public ra internet để xem từ điện thoại: dùng `ngrok http 5000` hoặc
deploy lên VPS/Render/Railway (nhớ đặt biến môi trường thay vì commit `.env`).

## 4C. Cập nhật lên bản mới nhất (Windows, chỉ 1 lệnh)

Thay vì tự làm nhiều bước (git pull, activate venv, cài lại thư viện, tắt
tiến trình cũ, chạy lại), dùng script có sẵn:

```powershell
.\update.ps1
```

Script này tự động làm toàn bộ các bước trên rồi khởi động lại app. Trình
duyệt cũng tự tải lại đúng CSS/JS mới (không cần Ctrl+Shift+R nữa).

## 4B. Chạy CLI (không cần trình duyệt)

```bash
python bot.py
```

Chạy nền đơn giản:

```bash
nohup python bot.py > bot.log 2>&1 &
```

## 5. Tùy chỉnh ngưỡng cảnh báo

Với **web app**: vào trang **Cài đặt**, sửa trực tiếp trên form.

Với **CLI** hoặc cấu hình ban đầu: sửa trong file `.env`:

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `TIMEFRAME` | Khung giờ xét dòng tiền (1h/6h/12h/24h/7d) | `1h` |
| `MIN_USD_THRESHOLD` | Ngưỡng USD tuyệt đối để coi là đột biến | `50000` |
| `MIN_MCAP_RATIO` | Ngưỡng tỷ lệ dòng tiền / market cap (bắt được cả coin nhỏ) | `0.015` (1.5%) |
| `TOP_N` | Số token top đầu lấy về mỗi lần quét | `30` |
| `POLL_INTERVAL_SECONDS` | Tần suất quét (giây) | `180` (3 phút) |
| `ALERT_COOLDOWN_SECONDS` | Chặn spam — không báo lại cùng 1 token trong X giây | `3600` (1 giờ) |

## Cơ chế hoạt động

- Gọi endpoint `/token/top` của Arkham API, xếp hạng token theo `inflowCex`
  (tiền vào sàn) và `outflowCex` (tiền ra sàn) trong khung giờ đã chọn —
  quét được **toàn bộ token**, không cần chỉ định trước danh sách.
- Token nào vượt ngưỡng USD tuyệt đối **hoặc** vượt tỷ lệ so với market cap
  → ghi vào lịch sử cảnh báo (hiện trên dashboard) + gửi Telegram (nếu bật),
  kèm cơ chế cooldown chống spam theo từng token.
- Web app chạy vòng quét trong 1 background thread song song với web server,
  dữ liệu cảnh báo lưu trong bộ nhớ (tối đa 500 cảnh báo gần nhất) — nếu
  restart app, lịch sử cảnh báo sẽ mất (cấu hình ngưỡng thì vẫn giữ vì đã
  ghi vào `.env`).

## Cấu trúc project

```
arkham-exchange-bot/
├── arkham_core.py     # Logic dung chung: goi API, phat hien dot bien, gui Telegram
├── app.py              # Web app (Flask) + background worker
├── bot.py               # Ban CLI, dung chung logic voi app.py
├── templates/           # Giao dien HTML (dashboard, settings)
├── static/               # CSS + JS phia client
├── requirements.txt
└── .env.example
```

## Giới hạn cần biết

- Endpoint `/token/top` là "heavy endpoint" (giới hạn 1 request/giây từ
  phía Arkham) — mỗi vòng quét chỉ gọi 2 request nên không lo bị chặn,
  nhưng đừng đặt `POLL_INTERVAL_SECONDS` quá nhỏ (dưới 30s không cần thiết).
- Web app dùng Flask dev server mặc định — đủ dùng cho cá nhân, nhưng nếu
  deploy public/nhiều người dùng nên chuyển sang `gunicorn` như hướng dẫn ở
  mục 4A.
- Đây không phải lời khuyên tài chính — chỉ là công cụ cảnh báo dữ liệu
  on-chain, quyết định giao dịch vẫn cần kết hợp thêm các yếu tố khác
  (giá, volume, funding rate, tin tức dự án...).

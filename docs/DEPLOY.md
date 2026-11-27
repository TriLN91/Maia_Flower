# 🚀 Deploy Maia_Flower lên Render (gói miễn phí)

## Kiến trúc

```
                    ┌──────────────────────── Render ───────────────────────┐
 Trình duyệt ──────▶│ Static Site "maia-flower-web" (CDN, không ngủ)         │
   │                │   web React — https://maia-flower-web.onrender.com     │
   │  fetch /api/v1 │                                                        │
   └───────────────▶│ Web service "maia-flower" (Docker, ngủ sau 15')        │
                    │   FastAPI /api/v1, /docs, /mock-gateway                │
                    │   + Celery worker + beat (chung container)             │
                    │        │                     │                         │
                    │  Postgres "maia-db"     Key Value "maia-redis"         │
                    └────────────────────────────────────────────────────────┘
```

- **Web là Static Site riêng** (miễn phí, phục vụ qua CDN, **không ngủ**): mở ra là thấy giao diện
  ngay. Nếu API đang ngủ, web hiện banner *"Máy chủ demo đang khởi động"* và dữ liệu tự hiện
  khi API thức (~1 phút) thay vì trắng trang.
- **API** chỉ còn backend. `FRONTEND_URL` trỏ về web → tự thêm vào CORS, cổng thanh toán trả khách
  về `/payment-result` của web, mở `/` của API thì chuyển sang web.
- Web biết địa chỉ API qua biến build `VITE_API_BASE_URL`. Request GET không gửi `Content-Type`
  nên là *simple request* — trình duyệt không phải gửi thêm `OPTIONS` (preflight) khi khác origin.
- **Celery chạy chung container với API** vì background worker của Render là gói trả phí
  (`RUN_WORKER_IN_WEB=true`). Muốn tách: tạo thêm *Background Worker* cùng image với lệnh
  `celery -A app.workers.celery_app worker --beat` và đặt `RUN_WORKER_IN_WEB=false`.
- **Chế độ demo** (`DEMO_MODE=true`): lần khởi động đầu tự sinh dữ liệu 12 tháng + tài khoản
  demo; mỗi sáng 06:00 (giờ VN) tự nhập hàng theo *gợi ý nhập hàng* của hệ thống.
- Vẫn có thể chạy **một dịch vụ** (API phục vụ luôn web): đặt `FRONTEND_DIST_DIR` tới một bản build
  Vite — FastAPI tự phục vụ `/assets` và fallback SPA.
- Toàn bộ hạ tầng khai báo trong [`render.yaml`](../render.yaml) (Blueprint).

**Trùng tên:** tên dịch vụ trên Render là duy nhất toàn cầu. Nếu URL thực tế khác
`maia-flower.onrender.com` / `maia-flower-web.onrender.com`, sửa `FRONTEND_URL` (dịch vụ API) và
`VITE_API_BASE_URL` (Static Site) cho khớp rồi deploy lại.

## Các bước (khoảng 10 phút)

1. Đăng nhập https://render.com bằng tài khoản GitHub.
2. **New → Blueprint** → chọn repo `Maia_Flower` → Render đọc `render.yaml` và liệt kê
   3 tài nguyên: `maia-db`, `maia-redis`, `maia-flower`.
3. Render hỏi các biến `sync: false`:
   - `DEMO_ACCOUNT_PASSWORD`: tự đặt một mật khẩu (dùng cho `owner@maiaflower.vn` và
     `tho@maiaflower.vn` — chỉ là tài khoản demo).
   - `GOONG_API_KEY`: để trống nếu chưa có.
4. **Apply** → đợi build (~5–8 phút lần đầu). Log sẽ có dòng `Seeded … demo accounts created`.
5. Mở `https://maia-flower-web.onrender.com` (web cho khách, `/admin` quản trị) và
   `https://maia-flower.onrender.com/docs` (Swagger).

Mỗi lần push lên `main`, Render tự build và deploy lại (dữ liệu giữ nguyên; seed chỉ chạy
khi database trống).

## Xử lý sự cố

| Triệu chứng trong log | Nguyên nhân | Cách sửa |
|---|---|---|
| `Cannot resolve the database host … SAME region` / `socket.gaierror: Name or service not known` | Web và Postgres/Key Value **khác region** (địa chỉ nội bộ chỉ phân giải trong cùng region; Render mặc định `oregon`) | `render.yaml` đặt `region: singapore` cho cả 3. Region không đổi được sau khi tạo → xóa tài nguyên sai region rồi tạo lại (xem dưới) |
| `Waiting for database…` lặp lại rồi hết 90 giây | Database mới tạo chưa sẵn sàng / đang bảo trì | Bấm **Manual Deploy** lại sau vài phút |
| `Refusing to seed demo data in production` | Thiếu `DEMO_MODE=true` | Thêm biến trong tab Environment |

**Tạo lại khi lỡ tạo sai region:** Dashboard → mở từng tài nguyên `maia-flower`, `maia-redis`,
`maia-db` → *Settings* → *Delete* (database còn trống nên không mất gì) → xóa Blueprint →
**New → Blueprint** chọn lại repo.

## Giới hạn của gói miễn phí

| Giới hạn | Ảnh hưởng | Cách xử lý |
|---|---|---|
| Web "ngủ" sau 15 phút không có truy cập | Lần mở đầu mất ~1 phút; job Celery tạm dừng khi ngủ | Chấp nhận cho demo; gói Starter không ngủ |
| Postgres miễn phí hết hạn sau 30 ngày | Mất dữ liệu demo | Tạo lại database (seed tự chạy lại) hoặc nâng cấp |
| RAM 512 MB | API + Celery (concurrency 1) vừa đủ | Tách worker khi nâng gói |

## Biến môi trường production

| Biến | Giá trị | Ghi chú |
|---|---|---|
| `APP_ENV` | `production` | |
| `DATABASE_URL` | từ `maia-db` | `postgres://…` được tự đổi sang driver asyncpg |
| `REDIS_URL` | từ `maia-redis` | broker Celery + rate limit + cache bản đồ |
| `JWT_SECRET`, `MOCK_PAY_SECRET` | Render tự sinh | |
| `DEMO_MODE` | `true` | seed khi trống + tự nhập hàng mỗi sáng |
| `MOCK_GATEWAY_ENABLED` | `true` | production mặc định **tắt** cổng giả lập; bản demo bật |
| `RUN_WORKER_IN_WEB` | `true` | Celery chạy chung container |
| `FRONTEND_URL` | URL Static Site | CORS + trang kết quả thanh toán + `/` chuyển sang web |
| `VITE_API_BASE_URL` (Static Site) | URL API | đặt lúc build web |
| `TRUST_PROXY_HEADERS` | `true` | lấy IP thật sau proxy của Render cho rate limit |
| `DEMO_ACCOUNT_PASSWORD` | bạn nhập | |
| `GOONG_API_KEY` | (tùy chọn) | không có thì tính đường chim bay × 1,3 |

## Đã kiểm tra trước khi deploy

Image production được chạy thử trên máy với cấu hình giống Render (database trống, URL dạng
`postgresql://…?sslmode=…`, `RENDER_EXTERNAL_URL`, `APP_ENV=production`):

- Chờ database (`wait-db`, báo rõ lỗi khác region) → migration → seed 12 tháng (7.295 đơn, sổ kho khớp 100%) → dự báo → tài khoản demo → Celery → API.
- Health check xanh; chạy bằng user không phải root.
- Chạy thử **khác origin** (web 4173 ↔ API 8081): CORS preflight cho POST + `Idempotency-Key`,
  đặt hàng → cổng giả lập trên API → quay về `/payment-result` của web; tạm dừng API → web vẫn hiện
  kèm banner, dữ liệu tự hiện khi API chạy lại; GET không còn kèm `OPTIONS`.
- Luồng đầu cuối: báo giá ship → đặt hàng → thanh toán qua cổng giả lập → quay về
  `/payment-result` cùng origin → đơn `paid`.

CI có job `docker` build image production ở mỗi lần push.

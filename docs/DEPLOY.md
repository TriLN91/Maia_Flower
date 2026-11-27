# 🚀 Deploy Maia_Flower lên Render (gói miễn phí)

## Kiến trúc

```
                ┌──────────────── Render ────────────────┐
 Trình duyệt ──▶│  Web service "maia-flower" (Docker)    │
                │   ├─ FastAPI: /api/v1, /docs, /mock-gateway
                │   ├─ Web React (bản build Vite) — cùng origin
                │   └─ Celery worker + beat (chạy chung container)
                │        │                │               │
                │  Postgres "maia-db"   Key Value "maia-redis"
                └────────────────────────────────────────┘
```

- **Một dịch vụ web** phục vụ cả API lẫn web → cùng tên miền, không cần CORS; URL công khai lấy
  tự động từ biến `RENDER_EXTERNAL_URL` mà Render cấp.
- **Celery chạy chung container** vì background worker của Render là gói trả phí
  (`RUN_WORKER_IN_WEB=true`). Muốn tách: tạo thêm *Background Worker* cùng image với lệnh
  `celery -A app.workers.celery_app worker --beat` và đặt `RUN_WORKER_IN_WEB=false`.
- **Chế độ demo** (`DEMO_MODE=true`): lần khởi động đầu tự sinh dữ liệu 12 tháng + tài khoản
  demo; mỗi sáng 06:00 (giờ VN) tự nhập hàng theo *gợi ý nhập hàng* của hệ thống để bản demo
  luôn còn hoa cho khách đặt thử.
- Toàn bộ hạ tầng khai báo trong [`render.yaml`](../render.yaml) (Blueprint).

## Các bước (khoảng 10 phút)

1. Đăng nhập https://render.com bằng tài khoản GitHub.
2. **New → Blueprint** → chọn repo `Maia_Flower` → Render đọc `render.yaml` và liệt kê
   3 tài nguyên: `maia-db`, `maia-redis`, `maia-flower`.
3. Render hỏi các biến `sync: false`:
   - `DEMO_ACCOUNT_PASSWORD`: tự đặt một mật khẩu (dùng cho `owner@maiaflower.vn` và
     `tho@maiaflower.vn` — chỉ là tài khoản demo).
   - `GOONG_API_KEY`: để trống nếu chưa có.
4. **Apply** → đợi build (~5–8 phút lần đầu). Log sẽ có dòng `Seeded … demo accounts created`.
5. Mở `https://<tên-dịch-vụ>.onrender.com` — web cho khách; `/admin` — quản trị; `/docs` — Swagger.

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
| `TRUST_PROXY_HEADERS` | `true` | lấy IP thật sau proxy của Render cho rate limit |
| `DEMO_ACCOUNT_PASSWORD` | bạn nhập | |
| `GOONG_API_KEY` | (tùy chọn) | không có thì tính đường chim bay × 1,3 |

## Đã kiểm tra trước khi deploy

Image production được chạy thử trên máy với cấu hình giống Render (database trống, URL dạng
`postgresql://…?sslmode=…`, `RENDER_EXTERNAL_URL`, `APP_ENV=production`):

- Chờ database (`wait-db`, báo rõ lỗi khác region) → migration → seed 12 tháng (7.295 đơn, sổ kho khớp 100%) → dự báo → tài khoản demo → Celery → API.
- Health check xanh; chạy bằng user không phải root.
- Web được phục vụ ở `/` và mọi đường dẫn của React Router (`/admin/kho`…); API sai đường dẫn
  trả 404 chứ không trả HTML.
- Luồng đầu cuối: báo giá ship → đặt hàng → thanh toán qua cổng giả lập → quay về
  `/payment-result` cùng origin → đơn `paid`.

CI có job `docker` build image production ở mỗi lần push.

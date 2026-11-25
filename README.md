# 🌸 Maia_Flower

Website bán hoa bó cho một cửa hàng. Backend được thiết kế quanh đặc tính **hoa là hàng mau hỏng**:

- **Tồn kho theo lô + FEFO:** biết từng cành hoa nhập ngày nào, luôn xuất lô sắp hết hạn trước, không bán vượt khi nhiều người đặt cùng lúc.
- **"Cần bán gấp" + giảm giá động:** tự giảm giá các mẫu dùng hoa sắp hết hạn, kèm rào chắn về biên lợi nhuận.
- **Dự báo nhu cầu theo mùa lễ:** gợi ý lượng hoa cần nhập trước 14/2, 8/3, 20/10, 20/11…

Tài liệu thiết kế đầy đủ: [docs/DESIGN.md](docs/DESIGN.md)

## Công nghệ

FastAPI · SQLAlchemy 2 (async) · PostgreSQL · Redis · Alembic · pytest · Docker Compose · GitHub Actions

## Chạy dự án

Yêu cầu: Docker Desktop.

```bash
cp .env.example .env          # rồi đặt JWT_SECRET ngẫu nhiên
docker compose up -d --build  # Postgres + Redis + API (tự chạy migration) + Celery worker
```

- API docs (Swagger): http://localhost:8000/docs
- Kiểm tra sức khỏe: http://localhost:8000/api/v1/health

Tạo tài khoản chủ shop đầu tiên (mật khẩu được hỏi ẩn):

```bash
docker compose exec api python -m app.cli create-owner --email owner@maiaflower.vn --name "Chủ shop"
```

Sau đó bấm **Authorize** trong Swagger, nhập email vào ô `username`.

### Dữ liệu demo

```bash
docker compose exec api python -m app.cli seed-demo --reset   # 365 ngày, --seed 42
```

Mô phỏng từng ngày: nhập lô theo lịch, đơn theo thứ trong tuần và ngày lễ (14/2, 8/3, 20/10, 20/11,
Ngày của Mẹ, Tết…), lấy hoa FEFO, hoa hỏng theo chất lượng nhà cung cấp, lô hết hạn bị bỏ.
Kết quả với `--seed 42` (12 tháng tới 24/11/2026): **7.346 đơn**, ngày đông nhất 14/2 (126 đơn),
hao hụt **13,5%**, sổ kho khớp 100%. *Đây là dữ liệu mô phỏng, không phải số liệu thật.*

### Thử thanh toán

1. Đặt đơn qua `POST /api/v1/shop/orders` → nhận `tracking_token`.
2. `POST /api/v1/shop/orders/track/{token}/pay` → mở `payment_url` trong trình duyệt.
3. Trang **cổng thanh toán giả lập** có các nút: thành công, thất bại, khách hủy, IPN đến trễ 2 phút,
   IPN gửi 2 lần — để thử mọi tình huống mà cổng thật có thể gây ra.

## Phát triển

```bash
docker compose exec api pytest -q                  # chạy test (DB test riêng, tự migrate)
docker compose exec api ruff format . && docker compose exec api ruff check .
docker compose exec api alembic revision --autogenerate -m "mô tả"   # tạo migration
```

Code trong `backend/` được mount vào container, sửa code là API tự reload.

### Định dạng lỗi

Mọi lỗi nghiệp vụ trả về cùng một dạng, frontend dựa vào `code` để xử lý:

```json
{"detail": "Flower type is used by active bouquet templates", "code": "FLOWER_IN_USE",
 "extra": {"templates": ["Đỏ Rực"]}}
```

> **Vì sao chạy Python trong Docker?** Một số máy Windows bật Smart App Control sẽ chặn các
> thư viện biên dịch sẵn (asyncpg, SQLAlchemy). Chạy trong container Linux tránh được việc này
> và giống môi trường deploy thật.

## Cấu trúc

```
backend/
  app/
    api/        # router FastAPI, dependency (auth, phân quyền)
    core/       # cấu hình, DB, bảo mật (JWT, argon2)
    models/     # SQLAlchemy models
    schemas/    # Pydantic schemas (request/response)
    services/   # logic nghiệp vụ
  alembic/      # migration
  tests/
docs/DESIGN.md
docker-compose.yml
```

## Tiến độ

- [x] **Ngày 1:** khung dự án, Docker, migration, CI, đăng nhập JWT + phân quyền staff/owner
- [x] **Ngày 2:** loại hoa, nhà cung cấp, mẫu bó hoa (công thức, lịch sử giá, slug tiếng Việt), API công khai cho khách
- [x] **Ngày 3:** nhập lô, sổ kho bất biến, độ tươi, hao hụt/kiểm kê, tồn kho tổng hợp, giá vốn mẫu + cảnh báo biên lợi nhuận (có test đồng thời)
- [x] **Ngày 4:** checkout không cần đăng nhập — FEFO cho cả giỏ, giữ hoa + khung giờ 15 phút, idempotency, theo dõi đơn (test 50 request đồng thời: không bán vượt)
- [x] **Ngày 5:** phí ship theo quãng đường (Goong + Haversine dự phòng, cache Redis), báo giá ship có chữ ký, cài đặt giao hàng, quản lý khung giờ + ghi đè theo ngày
- [x] **Ngày 6:** thanh toán qua cổng giả lập ký HMAC-SHA512 kiểu VNPay, IPN idempotent, thanh toán về trễ, job Celery nhả đơn quá hạn, quy trình đơn (state machine) + nhật ký trạng thái
- [x] **Ngày 7:** dữ liệu mô phỏng 12 tháng (tái lập bằng seed), job đêm đánh dấu lô quá hạn, API kiểm tra sổ kho, rate limit Redis (cửa sổ trượt, Lua nguyên tử)
- [ ] Ngày 8: "Cần bán gấp" + giảm giá động tự động
- [ ] …

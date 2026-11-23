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
docker compose up -d --build  # Postgres + Redis + API (tự chạy migration)
```

- API docs (Swagger): http://localhost:8000/docs
- Kiểm tra sức khỏe: http://localhost:8000/api/v1/health

Tạo tài khoản chủ shop đầu tiên (mật khẩu được hỏi ẩn):

```bash
docker compose exec api python -m app.cli create-owner --email owner@maiaflower.vn --name "Chủ shop"
```

Sau đó bấm **Authorize** trong Swagger, nhập email vào ô `username`.

## Phát triển

```bash
docker compose exec api pytest -q                  # chạy test (DB test riêng, tự migrate)
docker compose exec api ruff format . && docker compose exec api ruff check .
docker compose exec api alembic revision --autogenerate -m "mô tả"   # tạo migration
```

Code trong `backend/` được mount vào container, sửa code là API tự reload.

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
- [ ] Ngày 2: loại hoa, nhà cung cấp, mẫu bó hoa
- [ ] Ngày 3: nhập lô, sổ kho, độ tươi
- [ ] …

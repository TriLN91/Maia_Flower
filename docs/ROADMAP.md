# 🗺️ Maia_Flower — Báo cáo tiến độ & Kế hoạch chi tiết

> Cập nhật: 2026-11-23 · Thiết kế tổng thể: [DESIGN.md](DESIGN.md)
> Repo: https://github.com/TriLN91/Maia_Flower

---

## Phần 1 — Đã làm được gì

### 1.1 Giai đoạn thảo luận ý tưởng
| Việc | Kết quả |
|---|---|
| Brainstorm hướng dự án | Chốt: shop hoa bó, nặng backend, giải bài toán **hoa là hàng mau hỏng** |
| Chốt 10 quyết định thiết kế | Python/FastAPI · 1 cửa hàng · khách không cần đăng nhập · giỏ nhiều bó · giá mẫu admin nhập · phí ship theo khoảng cách (Goong) · khung giờ giao · thanh toán mock · giảm giá động tự động · 3D làm sau |
| Tài liệu thiết kế | `docs/DESIGN.md` v1.0: tính năng A/B/E, kiến trúc, sơ đồ DB, lộ trình |

### 1.2 Ngày 1 — Khung dự án ✅ (commit `5c57a57`, `8c37b22`)
| Hạng mục | Chi tiết |
|---|---|
| Hạ tầng | Docker Compose: Postgres 17 (kèm DB test riêng), Redis 7, API FastAPI chạy trong container, tự reload khi sửa code |
| Cấu trúc code | `api / core / models / schemas / services` — tách tầng rõ ràng |
| Database | SQLAlchemy 2 async + Alembic; migration đầu tiên tạo bảng `staff_users`; quy ước đặt tên constraint cố định |
| Đăng nhập | JWT cho thợ bó/chủ shop, mật khẩu băm argon2, chống dò email qua thời gian phản hồi, token bị vô hiệu ngay khi tài khoản bị khóa |
| Phân quyền | Chỉ owner quản lý nhân viên; owner không tự hạ quyền/tự khóa; luôn còn ≥ 1 owner (có khóa dòng chống race condition) |
| API | `GET /health`, `POST /auth/login`, `GET /auth/me`, `POST /auth/change-password`, `GET/POST/PATCH /staff` |
| Công cụ | Lệnh CLI tạo owner đầu tiên (mật khẩu nhập ẩn) |
| Kiểm thử | **17 test pass**, chạy trên DB thật đã migrate (downgrade → upgrade mỗi lần chạy) |
| CI | GitHub Actions: ruff format + lint → `alembic check` → pytest. **Đang xanh.** |
| Tài liệu | README (cách chạy, cấu trúc), DESIGN.md |

### 1.3 Vấn đề phát sinh & cách xử lý
| Vấn đề | Xử lý |
|---|---|
| Windows Smart App Control chặn DLL của `asyncpg`, `SQLAlchemy` | Chạy toàn bộ backend trong Docker (không chỉnh cài đặt bảo mật). Lệnh dạng `docker compose exec api ...` |
| Thư viện kiểm tra email từ chối domain `.local` | Dùng domain `maiaflower.vn` cho dữ liệu test |
| Git trên Windows đổi xuống dòng sang CRLF | Thêm `.gitattributes` ép LF |
| Cảnh báo Node.js 20 trên GitHub Actions | Nâng `checkout@v7`, `setup-python@v7` |

### 1.4 Tiến độ tổng
```
Ngày:  1  2  3  4  5  6  7  8  9  10 11 12 13 14
       ██ ██ ██ ██ ██ ██ ██ ░░ ░░ ░░ ░░ ░░ ░░ ░░     7/14 ngày (~50%)
```

---

## Phần 2 — Quy ước áp dụng cho mọi ngày tiếp theo

| Quy ước | Nội dung |
|---|---|
| **Tiền** | Lưu số nguyên **đồng VNĐ** (`BIGINT`), không dùng float |
| **Thời gian** | Lưu UTC (`timestamptz`); hiển thị và tính khung giờ theo `Asia/Ho_Chi_Minh` |
| **Xóa dữ liệu** | Dữ liệu đã được đơn hàng tham chiếu (hoa, mẫu, lô) → **xóa mềm** (`is_active=false`), không xóa cứng |
| **Snapshot** | Giá, giảm giá, phí ship, khoảng cách được chụp vào đơn lúc đặt |
| **Lỗi nghiệp vụ** | Service ném lỗi có mã → API trả 4xx với `code` máy đọc được (vd. `OUT_OF_STOCK`, `SLOT_FULL`) |
| **Định nghĩa "xong" một ngày** | Có migration · có test (cả trường hợp lỗi) · ruff sạch · `alembic check` sạch · CI xanh · cập nhật README/Swagger · commit theo tính năng |
| **API** | Tiền tố `/api/v1`; endpoint công khai cho khách ở `/api/v1/shop/...`, quản trị ở `/api/v1/admin/...` |

---

## Phần 3 — Kế hoạch chi tiết từng ngày

### 📦 Ngày 2 — Danh mục: loại hoa, nhà cung cấp, mẫu bó hoa ✅

**Bảng mới**
```
flower_types(id, name UNIQUE, color, reference_cost, vase_life_days >0, image_url, is_active, timestamps)
suppliers(id, name, phone, note, is_active, timestamps)
bouquet_templates(id, name, slug UNIQUE, description, image_url, price >0, discount_locked,
                  is_active, updated_by → staff_users, timestamps)
template_items(template_id, flower_type_id, quantity >0)   PK(template_id, flower_type_id)
template_price_history(id, template_id, old_price, new_price, changed_by, changed_at)
```

**API**
| Method | Endpoint | Quyền |
|---|---|---|
| GET/POST | `/admin/flower-types` | staff xem, owner sửa |
| PATCH | `/admin/flower-types/{id}` | owner |
| GET/POST/PATCH | `/admin/suppliers` | owner |
| GET/POST | `/admin/templates` | staff xem, owner sửa |
| GET/PATCH | `/admin/templates/{id}` | staff xem, owner sửa |
| PUT | `/admin/templates/{id}/items` (thay cả công thức) | owner |
| GET | `/admin/templates/{id}/price-history` | owner |
| GET | `/shop/templates` (chỉ mẫu đang bán, phân trang, lọc theo giá) | công khai |
| GET | `/shop/templates/{slug}` | công khai |

**Quy tắc nghiệp vụ**
- Mẫu phải có ≥ 1 loại hoa; không trùng loại hoa trong một mẫu; chỉ dùng loại hoa đang `is_active`.
- Đổi giá → tự ghi `template_price_history` (cùng transaction).
- Tắt một loại hoa đang được mẫu đang bán sử dụng → cảnh báo/ từ chối (trả danh sách mẫu bị ảnh hưởng).
- `slug` tự sinh từ tên tiếng Việt (bỏ dấu): "Pastel Ngọt Ngào" → `pastel-ngot-ngao`.

**Test cần có**: CRUD, phân quyền (staff/owner/khách), validate công thức, lịch sử giá, slug tiếng Việt, khách không thấy mẫu đã tắt.

**Xong khi**: owner tạo được mẫu "Pastel Ngọt Ngào" qua Swagger và khách xem được ở `/shop/templates`.

---

### 🌷 Ngày 3 — Nhập lô, sổ kho, độ tươi (tính năng A, phần 1) ✅

**Bảng mới**
```
batches(id, flower_type_id, supplier_id, quantity_received >0, quantity_available >=0,
        cost_per_stem, received_at, expected_expiry_at, freshness_override NULL|0..1,
        status[ACTIVE|NEEDS_REVIEW|DEPLETED|DISCARDED], created_by, timestamps)
        INDEX(flower_type_id, status, expected_expiry_at)   ← phục vụ FEFO
inventory_movements(id, batch_id, order_id NULL, type[IMPORT|RESERVE|RELEASE|WASTE|ADJUST],
                    quantity (âm/dương), reason, created_by NULL, created_at)
```

**API**
| Method | Endpoint | Ghi chú |
|---|---|---|
| POST | `/admin/batches` | Nhập lô; `expected_expiry_at` mặc định = nhận + vase_life |
| GET | `/admin/batches?flower_type_id=&status=` | Kèm độ tươi tính sẵn |
| PATCH | `/admin/batches/{id}` | Sửa hạn, hạ độ tươi thủ công |
| POST | `/admin/batches/{id}/waste` | Ghi hoa hỏng (số lượng + lý do) |
| POST | `/admin/batches/{id}/adjust` | Kiểm kê: nhập số đếm thực tế (owner) |
| POST | `/admin/batches/{id}/discard` | Bỏ phần còn lại, đóng lô (owner) |
| GET | `/admin/inventory` | Tổng hợp theo loại hoa: tồn, số cành sắp hết hạn, độ tươi TB |
| GET | `/admin/batches/{id}/movements` | Lịch sử sổ kho |
| GET | `/admin/templates/{id}/cost` | Giá vốn hiện tại + cảnh báo biên lợi nhuận |

**Quy tắc nghiệp vụ**
- Mọi thay đổi `quantity_available` **phải** đi kèm một dòng `inventory_movements` trong cùng transaction (viết một hàm duy nhất `apply_movement()` để không ai cập nhật trực tiếp).
- Bất biến: `quantity_available = Σ movements của lô` — có test kiểm tra.
- `freshness = clamp(1 − elapsed / (expiry − received), 0, 1)`, nếu có `freshness_override` thì lấy min.
- Giá vốn mẫu = Σ (số cành × giá nhập TB có trọng số của các lô còn hàng). Cảnh báo khi `price × (1 − trần_giảm) < giá_vốn × (1 + biên_tối_thiểu)`.

**Test**: nhập lô, ghi hỏng vượt tồn bị từ chối, bất biến sổ kho, độ tươi theo thời gian (dùng thời gian giả lập), giá vốn & cảnh báo.

**Xong khi**: nhập 3 lô hồng khác ngày, xem được độ tươi từng lô và tổng tồn.

> **Ghi chú khi làm:** bỏ loại movement `SELL` — bán xong không làm đổi số còn bán được (hoa đã bị trừ lúc giữ chỗ), trạng thái bán sẽ nằm ở `order_allocations` (ngày 4). Nhờ vậy bất biến *tồn = tổng sổ kho* luôn đúng. Trần giảm giá (30%) và biên tối thiểu (20%) tạm để trong cấu hình môi trường, ngày 8 chuyển sang `shop_settings`.

---

### 🛒 Ngày 4 — Checkout: FEFO + giữ hoa + giữ khung giờ (tính năng A, phần 2) ⭐ ✅

**Bảng mới**
```
delivery_slots(id, start_time, end_time, default_capacity, is_active)
delivery_slot_days(id, slot_id, date, capacity, reserved_count, is_closed)  UNIQUE(slot_id, date)
orders(id, code UNIQUE, tracking_token UNIQUE, idempotency_key UNIQUE,
       customer_name, customer_phone, recipient_name, recipient_phone,
       delivery_address, delivery_lat, delivery_lng, delivery_distance_km, delivery_fee,
       delivery_slot_day_id, card_message, note,
       subtotal, discount_total, total, status, hold_expires_at, timestamps)
order_items(id, order_id, template_id, quantity, unit_price_snapshot, discount_pct_snapshot)
order_allocations(id, order_item_id, batch_id, flower_type_id, quantity)
```
(Ngày 4 dùng phí ship cố định tạm thời; ngày 5 thay bằng phí theo khoảng cách.)

**API**
| Method | Endpoint | Ghi chú |
|---|---|---|
| POST | `/shop/cart/quote` | Tính lại giỏ: giá, giảm giá, còn hàng không — không giữ gì |
| GET | `/shop/delivery-slots?date=` | Khung giờ còn chỗ (đã áp quy tắc đặt trước ≥ 2h, ≤ 7 ngày) |
| POST | `/shop/orders` | Header `Idempotency-Key` bắt buộc; tạo đơn + giữ hoa + giữ khung giờ |
| GET | `/shop/orders/track/{token}` | Khách xem đơn |

**Thuật toán tạo đơn** (một transaction):
1. Kiểm tra idempotency key — đã có thì trả lại đơn cũ.
2. Tính lại giá từ DB (không tin client).
3. Gộp nhu cầu theo loại hoa.
4. `SELECT … FOR UPDATE` dòng `delivery_slot_days` → hết chỗ thì `SLOT_FULL`.
5. `SELECT … FOR UPDATE` các lô theo thứ tự `(flower_type_id, expected_expiry_at, id)`, chỉ lấy lô còn tươi tới giờ bắt đầu khung giao.
6. Phân bổ FEFO; thiếu bất kỳ loại nào → `OUT_OF_STOCK` kèm chi tiết, rollback toàn bộ.
7. Ghi movements `RESERVE`, allocations, tăng `reserved_count`, đặt `hold_expires_at = now + 15'`.
8. Sinh mã đơn `MF-YYMMDD-XXXX` và tracking token (`secrets.token_urlsafe(32)`).

**Test** ⭐:
- FEFO lấy đúng lô cũ trước, tràn sang lô sau.
- Không lấy lô sẽ hết hạn trước giờ giao.
- Thiếu một loại hoa → cả đơn thất bại, tồn kho không đổi.
- **Test đồng thời**: 50 request song song tranh 10 bó còn lại → đúng 10 đơn thành công, không âm kho, không deadlock.
- Gửi trùng idempotency key → một đơn duy nhất.
- Khung giờ đầy → từ chối.

**Xong khi**: đặt được đơn 3 bó qua Swagger, xem được lô nào bị trừ.

> **Ghi chú khi làm:**
> - Lô phải còn hạn tới **hết** khung giao (không chỉ lúc bắt đầu) — thận trọng hơn thiết kế ban đầu.
> - Lưu thêm `request_fingerprint`: cùng Idempotency-Key nhưng khác nội dung → 422 `IDEMPOTENCY_KEY_REUSED`.
> - Đơn lưu snapshot tên mẫu + giờ giao thực (`delivery_starts_at/ends_at`); mã đơn bỏ ký tự dễ nhầm (0/O, 1/I).
> - Migration tạo sẵn 5 khung giờ mặc định; khung theo ngày được tạo lười bằng `INSERT … ON CONFLICT DO NOTHING`.
> - Thêm sớm `GET /admin/orders/{id}` (xem phân bổ lô) — phần còn lại của quản lý đơn vẫn ở ngày 6.

---

### 🚚 Ngày 5 — Phí ship theo khoảng cách (Goong) + quản lý khung giờ ✅

**Việc cần bạn chuẩn bị trước ngày này**: đăng ký Goong, lấy **API key** và **Maptiles key**, đặt vào `.env` (`GOONG_API_KEY`, `GOONG_MAPTILES_KEY`). Chưa có thì hệ thống dùng Haversine.

**Thành phần**
- `DistanceProvider` (interface) → `GoongProvider` (AutoComplete, Place Detail, Distance Matrix, xe máy), `HaversineProvider` (× 1.3).
- Tự động chuyển sang Haversine khi Goong lỗi / timeout 3s / hết hạn mức; ghi log.
- Cache Redis: geocode 30 ngày, khoảng cách 7 ngày (khóa theo tọa độ làm tròn 4 chữ số).
- Bảng phí + phụ phí lễ + miễn phí ship theo `delivery_fee_tiers` và `shop_settings`.
- **Báo giá ship có chữ ký**: token HMAC chứa (tọa độ, khoảng cách, phí, hạn 15'). `POST /shop/orders` bắt buộc gửi token này.

**API**
| Method | Endpoint |
|---|---|
| GET | `/shop/address/autocomplete?q=` (proxy, rate limit theo IP) |
| GET | `/shop/address/place/{place_id}` |
| POST | `/shop/delivery/quote` → `{distance_km, fee, quote_token, expires_at}` |
| GET/POST/PATCH | `/admin/delivery-slots`, `/admin/delivery-slot-days` (ghi đè theo ngày) |
| GET/PUT | `/admin/settings/delivery` (bảng phí, bán kính, tọa độ shop) |

**Test**: các ví dụ phí trong DESIGN (7,4 km → 42.000đ; 12 km → 69.000đ), > 15 km bị từ chối, phụ phí lễ, miễn phí ship, token bị sửa/hết hạn, Goong lỗi → Haversine (mock HTTP bằng `respx`).

> **Ghi chú khi làm:**
> - Bảng phí lưu thành **một dòng JSON trong `shop_settings`** (kiểm tra bằng Pydantic) thay cho bảng `delivery_fee_tiers` — đổi cả bảng phí trong một lần, không có trạng thái nửa cũ nửa mới. Bảng này cũng sẽ chứa cài đặt giảm giá ở ngày 8.
> - Token báo giá chứa **tọa độ + quãng đường** (không chứa phí): lúc đặt hàng phí được tính lại từ quãng đường đã ký + giỏ hàng + ngày giao (phụ phí lễ, miễn phí ship). `OrderCreate` không còn nhận `delivery_lat/lng` từ client.
> - Ngày lễ cấu hình dạng `MM-DD`; Ngày của Mẹ (ngày thay đổi theo năm) để ngày 9 cùng bảng hệ số lễ.
> - **Chưa kiểm chứng với Goong thật**: trang tài liệu docs.goong.io lỗi chứng chỉ TLS lúc làm; client viết theo định dạng tương thích Google Places, test bằng respx. Cần chạy thử khi có `GOONG_API_KEY`.
> - Rate limit cho autocomplete dời sang ngày 7 (cùng các rate limit khác).
> - Không cho sửa giờ của khung đã có (đơn cũ tham chiếu) — tắt khung cũ, tạo khung mới; có kiểm tra chồng giờ.

---

### 💳 Ngày 6 — Thanh toán mock + job nền Celery + quy trình đơn ✅

**Thành phần**
- `PaymentProvider` (interface) → `MockProvider`.
- Trang thanh toán giả (HTML đơn giản do FastAPI trả) với nút: Thành công / Thất bại / Khách hủy / IPN trễ 2 phút / IPN gửi 2 lần.
- Ký **HMAC-SHA512** đúng định dạng VNPay (sắp xếp tham số, `vnp_SecureHash`).
- Endpoint IPN: xác minh chữ ký → kiểm tra số tiền → **idempotent** (theo `txn_ref`) → chuyển đơn `PAID`, movements `RESERVE → SELL`.
- IPN đến sau khi giữ chỗ hết hạn: thử giữ lại hoa; không được thì đánh dấu `PAID_NEEDS_REFUND` và báo owner.
- **Celery worker + beat** (thêm service vào docker-compose): job `release_expired_holds` mỗi phút.
- Quy trình đơn cho thợ: `PAID → PREPARING → DELIVERING → COMPLETED`, hủy đơn (nhả hoa nếu chưa bó). Kiểm soát chuyển trạng thái hợp lệ (state machine).

**API**
| Method | Endpoint |
|---|---|
| POST | `/shop/orders/{code}/pay` → URL thanh toán |
| GET | `/mock-pay/{txn_ref}` (trang giả) |
| GET | `/payments/mock/return` (trình duyệt quay về) |
| POST | `/payments/mock/ipn` (server-to-server) |
| GET | `/admin/orders?status=&date=` · `GET /admin/orders/{id}` (kèm lô cần lấy) |
| POST | `/admin/orders/{id}/transition` |

**Test**: chữ ký sai bị từ chối, sai số tiền, IPN trùng chỉ cộng 1 lần, IPN trễ, hết hạn giữ → nhả đúng lô, chuyển trạng thái không hợp lệ bị chặn.

> **Ghi chú khi làm:**
> - Tách `services/reservations.py` (giữ/nhả hàng) dùng chung cho checkout, job nhả đơn, hủy đơn, thanh toán về trễ. Thứ tự khóa thống nhất: *payment → order → slot_day → batches*.
> - IPN là GET và trả `{"RspCode","Message"}` theo quy ước VNPay (00/01/02/04/97/99). **Chỉ IPN đổi trạng thái đơn**; return URL chỉ hiển thị.
> - Thanh toán về trễ: chỉ "hồi sinh" đơn `EXPIRED` (giữ lại hoa + khung giờ trong SAVEPOINT); không được thì `NEEDS_REFUND`. Đơn chủ shop đã hủy không bị hồi sinh — khoản tiền được đánh dấu `needs_refund`.
> - Thêm trạng thái `needs_refund` (hủy đơn đã trả tiền / tiền về trễ) và bảng `order_events` (audit + timeline cho khách).
> - Endpoint thanh toán là `POST /shop/orders/track/{token}/pay` (cần tracking token, vì khách không đăng nhập). Cổng giả lập ở `/mock-gateway` (ngoài `/api/v1`), tắt khi `APP_ENV=production`.
> - Job nhả đơn dùng `SKIP LOCKED`, mỗi đơn một transaction; có test IPN và job chạy đua trên cùng đơn.
> - Dev chạy Celery `worker --beat` trong một container; production phải tách và chỉ chạy một beat.

---

### 🧪 Ngày 7 — Dữ liệu giả lập 12 tháng, job đêm, rate limit, dự phòng ✅

- **Script `scripts/seed_history.py`**: tạo ~15 loại hoa, 4 nhà cung cấp, ~12 mẫu bó, 5 khung giờ; mô phỏng 365 ngày nhập lô + đơn hàng với:
  - Cuối tuần × 1,4; ngày lễ × 3–8 (14/2 hồng đỏ cao nhất); mùa tốt nghiệp tháng 5–6.
  - Hao hụt ngẫu nhiên theo nhà cung cấp; mỗi đơn 1–3 bó.
  - Có tham số `--seed` để kết quả lặp lại được.
- **Job đêm** (Celery beat, 00:30 giờ VN): lô quá hạn → `NEEDS_REVIEW`; lô hết hàng → `DEPLETED`.
- **Rate limit Redis** (sliding window): đăng nhập 5 lần/phút/IP, tra đơn 10/phút, autocomplete 30/phút, tạo đơn 5/phút/SĐT.
- Thời gian còn lại: sửa lỗi, bổ sung test, dọn code tuần 1.

**Mốc cuối tuần 1**: toàn bộ luồng *nhập lô → khách đặt → thanh toán mock → thợ bó → hoàn thành* chạy được qua Swagger.

> **Ghi chú khi làm:**
> - Seed là lệnh `python -m app.cli seed-demo [--reset] [--days] [--end-date] [--seed]`, ghi thẳng bằng Core insert (365 ngày ≈ 15 giây), tự đặt lại sequence; từ chối chạy ở production và khi bảng đã có dữ liệu mà không có `--reset`. Dịp đông, chủ shop được coi như đã tăng sức chứa khung giờ.
> - Thêm `GET /admin/inventory/audit` kiểm tra bất biến tồn = tổng sổ kho trên mọi lô.
> - Rate limit dùng **cửa sổ trượt** (sorted set + script Lua nguyên tử), trả 429 + `Retry-After`; Redis lỗi thì cho qua (fail-open). Chỉ đọc `X-Forwarded-For` khi bật `TRUST_PROXY_HEADERS`. Giới hạn: đăng nhập 5/phút/IP + 10/15 phút/email; tạo đơn 20/phút/IP + 5/10 phút/SĐT; theo dõi đơn 30/phút; thanh toán 10/phút; gợi ý địa chỉ/địa điểm 30/phút; báo giá ship 20/phút; báo giá giỏ 60/phút.
> - **Sửa lỗi phát hiện khi chạy test lặp:** dấu vân tay idempotency có chứa token báo giá ship (ký lại mỗi giây) → khách lấy lại báo giá rồi đặt lại bị 422. Nay bỏ token khỏi dấu vân tay.

---

### 🔥 Ngày 8 — Tính năng B: "Cần bán gấp" + giảm giá động tự động

**Bảng mới**: `pricing_rules`, `urgency_scores`, `template_discounts`, `template_discount_log` (+ settings: trần giảm, biên tối thiểu, bước tối đa ±10đ%, kill switch, N ngày).

**Job `recompute_urgency`** (mỗi đêm + khi nhập lô + khi đơn lớn):
1. Mỗi loại hoa: `sắp_hết_hạn`, `nhu_cầu_dự_kiến` (từ E; ngày 8 chưa có E thì tạm dùng TB 7 ngày), `dư_thừa`, `mức_giảm_hoa`.
2. Mỗi mẫu: `giảm_mẫu` = TB có trọng số theo số cành → áp trần → áp sàn biên lợi nhuận → giới hạn bước ±10 → bỏ qua mẫu `discount_locked` → kill switch.
3. Ghi `template_discounts` + log lý do (JSON: hoa nào, dư bao nhiêu, dự báo bao nhiêu).

**API**
| Method | Endpoint |
|---|---|
| GET | `/shop/templates/fresh-today` (mục "Tươi nhất hôm nay") |
| GET | `/shop/templates` (giờ trả kèm `discount_pct`, `final_price`) |
| GET | `/admin/urgency` (bảng hoa cần bán gấp) |
| GET | `/admin/templates/{id}/discount-log` |
| PUT | `/admin/settings/pricing` |
| POST | `/admin/pricing/recompute` (chạy tay) |

**Test**: ví dụ 12 cành/5 hồng giảm 20% → 8%; chạm sàn biên lợi nhuận; bước ±10; mẫu khóa; kill switch; hết dư thừa → gỡ giảm giá; giá đã snapshot trong đơn cũ không đổi.

---

### 📈 Ngày 9 — Tính năng E: Dự báo nhu cầu + gợi ý nhập hàng

**Bảng mới**: `holiday_factors`, `demand_forecasts`.

- Quy đổi lịch sử bán theo mẫu → **số cành theo loại hoa theo ngày** (từ `order_allocations`).
- Mô hình v1: `nền(thứ trong tuần, 4–8 tuần gần nhất) × hệ_số_lễ`.
- Hệ số lễ seed sẵn: 14/2, 8/3, 30/4–1/5, Ngày của Mẹ, 1/6, 20/10, 20/11, 24/12, Tết (âm lịch — tra bảng ngày dương theo năm), mùa tốt nghiệp.
- Job đêm: dự báo 14 ngày tới cho mọi loại hoa → `demand_forecasts`.
- **Gợi ý nhập hàng**: `cần_nhập = dự_báo(D … D+vase_life) + tồn_an_toàn − tồn_còn_dùng_được`.
- **Backtest**: chạy trượt trên dữ liệu giả lập, tính **MAPE** tổng và theo loại hoa; in bảng ra README.
- Nối E vào B (thay giá trị tạm của ngày 8).

**API**: `GET /admin/forecast?flower_type_id=&days=14`, `GET /admin/restock-suggestions?date=`, `GET/POST/PATCH /admin/holiday-factors`, `GET /admin/forecast/backtest`.

**Test**: công thức với dữ liệu nhỏ biết trước đáp án, hệ số lễ áp đúng ngày, gợi ý nhập không âm, MAPE tính đúng.

---

### 📱 Ngày 10–11 — Frontend cho khách (React + Vite + Tailwind, mobile-first)

**Khởi tạo**: `frontend/`, React Router, TanStack Query, client API sinh từ OpenAPI (hoặc viết tay gọn), thêm service `web` vào docker-compose, thêm job CI build frontend.

**Màn hình**
| Màn hình | Nội dung |
|---|---|
| Trang chủ | Banner, mục **"Tươi nhất hôm nay"**, danh sách mẫu (giá gốc gạch ngang + giá giảm) |
| Chi tiết mẫu | Ảnh, mô tả, thành phần hoa, chọn số lượng, thêm vào giỏ |
| Giỏ hàng | Lưu localStorage; gọi `/cart/quote` để cập nhật giá & báo hết hàng |
| Giao hàng | Ô địa chỉ có gợi ý (Goong), bản đồ ghim vị trí, phí ship, chọn ngày + khung giờ |
| Thông tin & thanh toán | Tên, SĐT, người nhận, lời nhắn thiệp → tạo đơn → chuyển sang trang thanh toán mock |
| Kết quả | Thành công/thất bại, mã đơn, link theo dõi |
| Theo dõi đơn | Trạng thái theo thời gian, ảnh mẫu, thông tin giao |

**Yêu cầu chất lượng**: dùng tốt ở màn 375px, nút ≥ 44px, có trạng thái loading/lỗi/rỗng, đếm ngược 15 phút giữ hoa, chặn bấm "Đặt hàng" 2 lần.

---

### 🛠️ Ngày 12 — Frontend quản trị (tối giản)

| Màn hình | Nội dung |
|---|---|
| Đăng nhập | JWT, tự đăng xuất khi hết hạn |
| Tổng quan | Đơn hôm nay theo khung giờ, cảnh báo cần bán gấp, lô cần kiểm tra |
| Đơn hàng | Danh sách theo trạng thái, chi tiết + **danh sách lô cần lấy**, nút chuyển trạng thái |
| Kho | Nhập lô, tồn theo lô + thanh độ tươi màu, ghi hỏng |
| Mẫu & giá | Sửa mẫu, công thức, giá, cảnh báo biên lợi nhuận, nhật ký giảm giá |
| Dự báo | Biểu đồ dự báo 14 ngày, gợi ý nhập hàng |
| Cài đặt | Khung giờ, phí ship, giảm giá, nhân viên (owner) |

---

### 🚀 Ngày 13 — Deploy & tài liệu

- Chọn nền tảng (đề xuất **Render** hoặc **Railway**: có Postgres + Redis + worker). **Bạn cần tạo tài khoản** trước ngày này.
- Dockerfile production (không cài dev deps), biến môi trường production, `APP_ENV=production` tắt `/docs` công khai hoặc giữ cho nhà tuyển dụng xem (quyết định khi tới).
- Chạy migration khi deploy, seed dữ liệu demo + tài khoản demo chỉ-xem.
- CI: deploy tự động khi `main` xanh.
- README hoàn chỉnh: sơ đồ kiến trúc (Mermaid), ảnh chụp màn hình, link demo, tài khoản demo, bảng MAPE, kết quả test tải, phần "Những bài toán khó đã giải".

---

### 🎬 Ngày 14 — Kiểm thử tải, dự phòng, demo

- **Test tải bằng Locust** (Python): kịch bản 200 người dùng đặt hàng cùng lúc tranh hoa giới hạn → ghi lại RPS, p95, xác nhận 0 lần bán vượt.
- Sửa lỗi tồn đọng, dọn code, kiểm tra bảo mật cơ bản (header, CORS, rate limit, secret).
- Quay video demo 2–3 phút: khách đặt trên điện thoại → thanh toán → admin thấy đơn → hoa sắp hết hạn tự giảm giá.
- Điền số thật vào câu CV (mục 6 DESIGN.md).

---

## Phần 4 — Việc bạn cần làm (không làm hộ được)

| Hạn | Việc |
|---|---|
| Trước ngày 5 | Đăng ký Goong, lấy API key + Maptiles key |
| Trước ngày 7 | Chọn địa chỉ shop mẫu (để tính phí ship trong dữ liệu demo) |
| Trước ngày 10 | (Tùy chọn) Chuẩn bị ảnh hoa/mẫu bó — nếu không, dùng ảnh miễn phí bản quyền |
| Trước ngày 13 | Tạo tài khoản Render hoặc Railway |
| Mỗi ngày | Xem lại commit, góp ý trước khi sang ngày kế tiếp |

---

## Phần 5 — Rủi ro & phương án

| Rủi ro | Khả năng | Phương án |
|---|---|---|
| Ngày 4 (FEFO đồng thời) tốn hơn 1 ngày | Cao | Ngày 7 là đệm; nếu cần, lùi rate limit sang ngày 13 |
| Goong lỗi / chưa có key | Trung bình | Haversine dự phòng sẵn có từ đầu |
| Frontend 2 ngày không đủ | Cao | Thứ tự hy sinh: bản đồ ghim → chỉ ô địa chỉ; admin → dùng Swagger cho phần ít dùng |
| Dữ liệu giả lập không thực tế → MAPE vô nghĩa | Trung bình | Ghi rõ trong README là dữ liệu mô phỏng; nêu cách đánh giá trên dữ liệu thật |
| Deploy free tier ngủ đông / giới hạn | Trung bình | Ghi chú "lần đầu mở mất ~30s"; giữ video demo làm dự phòng |
| Smart App Control chặn thêm công cụ (Node?) | Thấp | Chạy frontend trong Docker nếu cần |

---

## Phần 6 — Sau 2 tuần (giai đoạn 2)

1. **Shop 3D** bằng React Three Fiber: không gian cửa hàng, kệ nổi bật lấy từ bộ máy "Cần bán gấp", bàn bó hoa xem trước.
2. **VNPay sandbox thật** (chỉ thêm `VNPayProvider`).
3. Thay hoa thông minh theo vai trò (C), ảnh xác nhận bó hoa (F), chấm điểm nhà cung cấp (G).
4. Thông báo Zalo/SMS khi đơn đổi trạng thái.
5. Dự báo bằng ML (Prophet / gradient boosting), so sánh MAPE với v1.

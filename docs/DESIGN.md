# 🌸 Maia_Flower — Tài liệu thiết kế (v1.0)

> Trạng thái: **thiết kế đã chốt, sẵn sàng code.**
> Phạm vi: 2 tuần · Backend Python · 1 cửa hàng · Khách chọn theo mẫu có sẵn · Không cần đăng nhập khi mua · Giỏ hàng nhiều bó · Phí ship theo khoảng cách · Thanh toán **mock** (chuẩn bị sẵn để thay VNPay) · Shop 3D làm sau.

### Nhật ký quyết định
| # | Quyết định | Ngày |
|---|---|---|
| 1 | Tên dự án: **Maia_Flower** (repo: `maia-flower`) | 2026-11-23 |
| 2 | Thanh toán: **mock sandbox tự viết** trước, mô phỏng đúng luồng VNPay; thay VNPay thật sau | 2026-11-23 |
| 3 | Khách **không cần đăng nhập** (guest checkout); chỉ thợ bó và chủ shop đăng nhập | 2026-11-23 |
| 4 | **Phí giao hàng tính theo khoảng cách** | 2026-11-23 |
| 5 | **Một đơn có nhiều bó** (giỏ hàng) | 2026-11-23 |
| 6 | **Giá mẫu bó do admin nhập tay**; giảm giá động áp lên giá đó | 2026-11-23 |
| 7 | Bản đồ: **Goong** (gợi ý địa chỉ + quãng đường thực tế), Haversine làm dự phòng | 2026-11-23 |
| 8 | Bảng phí ship: dùng **số mẫu** (mục 3.6), admin sửa được | 2026-11-23 |
| 9 | Giờ giao: theo **khung giờ** có giới hạn số đơn | 2026-11-23 |
| 10 | Giảm giá động: **tự động áp dụng**, có rào chắn an toàn | 2026-11-23 |

---

## 1. Tóm tắt

Website bán hoa bó cho **một cửa hàng**. Khách chọn **các mẫu bó có sẵn** cho vào giỏ, nhập địa chỉ để tính phí ship, thanh toán online, rồi thợ bó và giao.

Điểm khác biệt nằm ở backend, được thiết kế quanh đặc tính **hoa là hàng mau hỏng**:

| Mã | Tính năng | Giải quyết vấn đề gì |
|---|---|---|
| **A** | Tồn kho theo **lô** + xuất kho **FEFO** | Biết chính xác hoa nào nhập ngày nào, còn tươi bao lâu; luôn dùng hoa sắp hết hạn trước |
| **B** | Bộ máy **"Cần bán gấp"** + giảm giá động | Tự đẩy mẫu dùng hoa sắp héo lên đầu, giảm giá có kiểm soát → giảm hao hụt |
| **E** | **Dự báo nhu cầu** theo ngày lễ + gợi ý nhập hàng | Nhập đúng lượng trước 14/2, 8/3, 20/10, 20/11… |

**Liên kết giữa ba phần:** E dự báo nhu cầu → B dùng dự báo để biết hoa nào sẽ **thừa** trước khi hết hạn → A đảm bảo khi bán thì lấy đúng lô sắp hết hạn.

---

## 2. Vai trò người dùng

| Vai trò | Đăng nhập? | Làm được gì |
|---|---|---|
| **Khách** | ❌ Không | Xem mẫu, mục "Tươi nhất hôm nay", thêm vào giỏ, nhập địa chỉ, thanh toán, theo dõi đơn qua link bí mật |
| **Thợ bó** (staff) | ✅ | Xem đơn cần bó, xem lấy hoa từ lô nào, cập nhật trạng thái, ghi nhận hoa hỏng |
| **Chủ shop** (owner) | ✅ | Mọi quyền của thợ + nhập lô, quản lý loại hoa / mẫu / giá / nhà cung cấp, cấu hình phí ship & giảm giá, xem cảnh báo và dự báo |

---

## 3. Tính năng chi tiết

### 3.1 Phần nền
- Đăng nhập JWT **chỉ cho staff/owner**, phân quyền theo vai trò.
- Loại hoa: tên, màu, **giá vốn tham khảo**, **số ngày tươi tiêu chuẩn** (vase life), ảnh.
- Nhà cung cấp.
- Mẫu bó hoa: tên, mô tả, ảnh, **giá bán do admin nhập**, **công thức cố định** (vd. 5 hồng + 3 baby + 4 bạch đàn).
  - **Cảnh báo biên lợi nhuận:** khi admin nhập/sửa giá, hệ thống tính **giá vốn hiện tại** của mẫu (từ giá nhập của các lô đang có) và cảnh báo nếu giá bán (kể cả sau giảm tối đa) thấp hơn giá vốn hoặc biên lợi nhuận < ngưỡng cấu hình.
- Đơn hàng: `CHỜ_THANH_TOÁN → ĐÃ_THANH_TOÁN → ĐANG_BÓ → ĐANG_GIAO → HOÀN_THÀNH` (+ `ĐÃ_HỦY`, `HẾT_HẠN`).

### 3.2 Mua hàng không cần đăng nhập (guest checkout)
- **Giỏ hàng lưu ở trình duyệt** (localStorage). Server **không tin giỏ hàng từ client**: khi checkout sẽ tính lại toàn bộ giá, giảm giá, tồn kho, phí ship.
- Khi đặt, khách nhập: tên, số điện thoại, địa chỉ nhận, giờ giao mong muốn, lời nhắn thiệp (tùy chọn), tên người nhận nếu là quà.
- Sau khi đặt, khách nhận:
  - **Mã đơn dễ đọc**, vd. `MF-251123-7K2Q`
  - **Link theo dõi bí mật** chứa token ngẫu nhiên (vd. `/track/<token>`), không đoán được.
- Tra cứu đơn thủ công: **mã đơn + 4 số cuối điện thoại**, có **giới hạn tần suất** (rate limit) để chống dò.
- **Idempotency key** cho nút "Đặt hàng": khách bấm 2 lần hoặc mạng chập chờn gửi lại cũng không tạo 2 đơn.
- Chống spam đơn ảo giữ hết hoa: rate limit theo IP/số điện thoại + mỗi đơn chưa thanh toán chỉ giữ hoa 15 phút.

### 3.3 A — Tồn kho theo lô + FEFO
- Mỗi lần nhập tạo một **lô** (`batch`): loại hoa, nhà cung cấp, số cành, giá nhập, ngày nhập, **ngày hết hạn dự kiến** (= ngày nhập + vase life, chủ shop sửa được).
- **Mọi thay đổi tồn kho đều ghi vào sổ** (`inventory_movement`): nhập, giữ chỗ, bán, nhả giữ chỗ, hỏng/héo, điều chỉnh. → truy vết được, tính được hao hụt.
- **Độ tươi** của lô: `freshness = 1 − (thời gian đã qua / tổng thời gian tươi)`, giới hạn [0, 1]. Thợ có thể hạ độ tươi thủ công.
- **Phân bổ FEFO cho cả giỏ hàng:**
  1. Gộp nhu cầu của **tất cả các bó** trong đơn theo loại hoa (vd. 2 bó Pastel + 1 bó Đỏ Rực → cần 13 hồng, 6 baby…).
  2. Trong **một transaction**, khóa các lô liên quan theo **thứ tự cố định (flower_type_id, batch_id)** để tránh deadlock.
  3. Với mỗi loại hoa, lấy từ lô **hết hạn sớm nhất mà vẫn còn tươi tới giờ giao** trước, thiếu thì lấy tiếp lô sau.
  4. Thiếu bất kỳ loại nào → **từ chối cả đơn** (all-or-nothing), báo rõ mẫu nào không đủ hoa.
- **Giữ hoa khi chờ thanh toán:** trừ `quantity_available`, ghi phân bổ, đặt hạn giữ 15 phút.
  - Thanh toán thành công → xác nhận.
  - Quá hạn → job nền nhả hoa về **đúng lô cũ**, đơn chuyển `HẾT_HẠN`.
- **Job đêm:** lô quá hạn → `CẦN_KIỂM_TRA`, chủ shop xác nhận bỏ (ghi hao hụt) hoặc gia hạn.

### 3.4 B — "Cần bán gấp" + giảm giá động
Vì giá mẫu do admin nhập tay, giảm giá động **áp lên giá mẫu**, không tính lại từ giá từng cành.

**Bước 1 — Điểm gấp của từng loại hoa** (chạy mỗi đêm + khi nhập lô / có đơn lớn):
```
sắp_hết_hạn     = số cành còn bán được thuộc các lô hết hạn trong N ngày tới (mặc định N = 2)
nhu_cầu_dự_kiến = tổng dự báo bán trong N ngày tới   ← lấy từ E
dư_thừa         = max(0, sắp_hết_hạn − nhu_cầu_dự_kiến)
mức_giảm_hoa    = theo bảng bậc (chỉ khi dư_thừa > 0), vd. ≤2 ngày: 10%, ≤1 ngày: 20%
```

**Bước 2 — Giảm giá của từng mẫu bó:**
```
giảm_mẫu = Σ (số_cành_hoa_i trong công thức × mức_giảm_hoa_i) / tổng_số_cành_của_mẫu
           → làm tròn, giới hạn bởi trần giảm (vd. 30%) và sàn biên lợi nhuận
```
Ví dụ mẫu 12 cành, trong đó 5 cành hồng đang giảm 20% → giảm mẫu ≈ 5×20/12 ≈ **8%**.

**Bước 3 — Tự động áp dụng, có rào chắn:**
- **Trần giảm** cho mỗi mẫu (mặc định 30%).
- **Sàn biên lợi nhuận:** giá sau giảm không bao giờ thấp hơn `giá vốn × (1 + biên tối thiểu)`; chạm sàn thì dừng ở sàn.
- **Giới hạn biến động:** mỗi lần chạy, mức giảm của một mẫu chỉ được đổi tối đa ±10 điểm % để giá không nhảy loạn.
- **Khóa theo mẫu:** admin có thể đánh dấu mẫu "không giảm giá" (vd. mẫu cao cấp).
- **Công tắc tổng (kill switch):** tắt toàn bộ giảm giá động bằng một cấu hình.
- **Nhật ký:** mỗi lần thay đổi ghi lại lý do (hoa nào, dư bao nhiêu, dự báo bao nhiêu) → admin xem được vì sao mẫu đang giảm.
- Hết dư thừa (đã bán hết lô sắp hạn) → lần chạy kế tiếp tự gỡ giảm giá.

**Bước 4 — Dùng kết quả:**
1. **Mục "Tươi nhất hôm nay":** xếp mẫu theo số cành "cần bán gấp" mà mẫu đó tiêu thụ.
2. **Báo cho chủ shop:** *"Còn 40 cành cẩm tú cầu, hết hạn sau 2 ngày, dự kiến chỉ bán được 15 → đã giảm 8% cho 3 mẫu."*
3. (Sau này) kệ nổi bật trong shop 3D lấy dữ liệu từ đây.

**Giá và giảm giá luôn được chốt (snapshot) vào đơn lúc đặt.**

### 3.5 E — Dự báo nhu cầu + gợi ý nhập hàng
- Dự án mới chưa có dữ liệu → **script sinh dữ liệu giả lập 12 tháng** (cuối tuần đông hơn, đột biến ngày lễ, nhiều bó/đơn).
- **Dự báo theo mẫu bó → quy đổi ra cành** qua công thức (vì khách mua theo mẫu).
- **Mô hình v1:**
  ```
  dự_báo(hoa, ngày) = nền(hoa, thứ_trong_tuần) × hệ_số_lễ(ngày)
  nền      = trung bình số cành bán vào cùng thứ đó trong 4–8 tuần gần nhất
  hệ_số_lễ = bảng cấu hình: 14/2, 8/3, 20/10, 20/11, Ngày của Mẹ, Tết, mùa tốt nghiệp…
  ```
- **Gợi ý nhập hàng** cho ngày D: `cần_nhập = dự_báo(D … D + vase_life) + tồn_an_toàn − tồn_còn_dùng_được_tới_ngày_đó`
- **Backtest + MAPE** để có con số cụ thể.
- (Sau này) thay bằng ML (Prophet / gradient boosting) mà không đổi API.

### 3.6 Phí giao hàng theo khoảng cách
- Shop lưu **tọa độ cửa hàng**. Khách nhập địa chỉ (gợi ý tự động) hoặc **ghim vị trí trên bản đồ** → có tọa độ.
- **Server tự tính khoảng cách và phí**, không nhận phí từ client.
- **Bảng phí mẫu** (admin sửa được, tính theo **quãng đường thực tế**, làm tròn lên 0,1 km):
  | Quy tắc | Giá trị mẫu |
  |---|---|
  | 3 km đầu | **20.000đ** (đồng giá) |
  | Từ km thứ 3 đến km thứ 10 | **+5.000đ / km** |
  | Từ km thứ 10 đến km thứ 15 | **+7.000đ / km** |
  | Trên 15 km | **Không nhận giao** |
  | Phụ phí ngày lễ (14/2, 8/3, 20/10, 20/11…) | **+20%** phí ship |
  | Miễn phí ship | Đơn từ **1.500.000đ** và quãng đường ≤ 5 km |

  Ví dụ: 7,4 km → 20.000 + 4,4 × 5.000 = **42.000đ**; 12 km → 20.000 + 7 × 5.000 + 2 × 7.000 = **69.000đ**.
- **Kiến trúc nhà cung cấp bản đồ có thể thay thế** (giống thanh toán):
  - `GoongProvider` (chính): **Place AutoComplete** để gợi ý địa chỉ, **Place Detail / Geocode** để lấy tọa độ, **Distance Matrix** để lấy quãng đường xe máy thực tế.
  - `HaversineProvider` (dự phòng + test): đường chim bay × hệ số đường vòng (~1.3), chạy offline; tự dùng khi Goong lỗi hoặc hết hạn mức.
- **Bảo vệ API key:** gợi ý địa chỉ và tính khoảng cách đều **gọi qua backend** (không lộ API key ra trình duyệt), có rate limit theo IP. Frontend chỉ dùng **Maptiles key** riêng của Goong để hiển thị bản đồ ghim vị trí.
- **Cache** kết quả geocode/khoảng cách trong Redis để giảm số lần gọi API.
- **Báo giá ship có hạn** (vd. 15 phút, ký bằng HMAC): khách xem phí ở bước nhập địa chỉ, lúc đặt hàng server kiểm tra báo giá còn hiệu lực và đúng địa chỉ.
- Phí ship được **snapshot** vào đơn cùng khoảng cách đã tính.

### 3.6b Khung giờ giao hàng
- Admin định nghĩa khung giờ mẫu: **8–10h, 10–12h, 13–15h, 15–17h, 17–19h**, mỗi khung **tối đa 6 đơn** (sửa được).
- **Ghi đè theo ngày:** ngày lễ tăng sức chứa (vd. 15 đơn/khung) hoặc đóng một khung/ngày nghỉ.
- **Thời gian chuẩn bị tối thiểu:** chỉ đặt được khung bắt đầu sau thời điểm hiện tại **≥ 2 giờ**; cho đặt trước tối đa **7 ngày**.
- **Giữ chỗ khung giờ cùng lúc với giữ hoa:** trong cùng transaction checkout, khóa dòng `delivery_slot_days` và tăng `reserved_count`; hết chỗ → từ chối, gợi ý khung gần nhất còn trống. Hết hạn giữ 15 phút → nhả cả hoa lẫn khung giờ.
- **FEFO dùng giờ bắt đầu của khung** để quyết định lô nào còn đủ tươi tới lúc giao.
- **E dùng dữ liệu khung giờ** sau này để gợi ý tăng sức chứa vào ngày lễ.

### 3.7 Thanh toán: mock sandbox → VNPay
- Định nghĩa interface `PaymentProvider`: `create_payment(order) → redirect_url`, `verify_callback(params) → kết quả`.
- **`MockProvider` (làm trong 2 tuần):**
  - Có **trang thanh toán giả** với các nút: *Thành công*, *Thất bại*, *Khách hủy*, *IPN đến trễ*, *IPN gửi trùng 2 lần*.
  - **Ký HMAC-SHA512 y như VNPay**, nên code xác minh chữ ký, idempotency, kiểm tra số tiền… là **code thật**, không phải code giả.
  - Không cần tunnel, không cần đăng ký tài khoản, test tự động được.
- **`VNPayProvider` (sau này):** chỉ thêm class mới + cấu hình `TMN_CODE` / `HASH_SECRET`, không sửa logic đơn hàng.

---

## 4. Kiến trúc & công nghệ

```
┌───────────────┐      ┌──────────────────────────────────────┐
│ React + Vite  │─────▶│ FastAPI (REST, OpenAPI/Swagger)      │
│ (mobile-first)│◀─────│  ├─ catalog / cart-checkout / orders │
│ khách + admin │      │  ├─ inventory (lô, FEFO, sổ kho)     │
└───────────────┘      │  ├─ pricing (B)                      │
                       │  ├─ forecasting (E)                  │
 Mock pay / VNPay ────▶│  ├─ payments  (PaymentProvider)      │
 Map API ◀────────────▶│  └─ delivery  (DistanceProvider)     │
                       └──────┬─────────────────┬─────────────┘
                              │                 │
                        ┌─────▼─────┐     ┌─────▼─────┐   ┌────────────────┐
                        │PostgreSQL │     │  Redis    │◀──│ Celery worker  │
                        └───────────┘     └───────────┘   │ + Celery beat  │
                                    (cache, rate limit,   └────────────────┘
                                     broker cho Celery)
```

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| API | **FastAPI** | Async, tự sinh Swagger, phổ biến trong tuyển dụng Python backend |
| ORM / migration | SQLAlchemy 2.0 + Alembic | Chuẩn công nghiệp |
| Database | **PostgreSQL** | Transaction + khóa dòng cho FEFO |
| Cache / rate limit / broker | **Redis** | Một dịch vụ, ba việc |
| Job nền | **Celery + Celery beat** | Nhả giữ chỗ, điểm gấp, dự báo, quét lô hết hạn |
| Dự báo | pandas | Đủ cho v1 |
| Test | pytest (+ test đồng thời cho FEFO, test luồng thanh toán mock) | Chứng minh không bán vượt, không cộng tiền trùng |
| Frontend | React + Vite + Tailwind (+ thư viện bản đồ cho ghim vị trí) | Sau này thêm React Three Fiber cho 3D |
| Hạ tầng | Docker Compose, GitHub Actions CI | Chạy 1 lệnh, có CI |
| Deploy | Render / Railway / Fly.io | Có URL công khai cho nhà tuyển dụng |

**Cấu trúc thư mục dự kiến**
```
maia-flower/
├─ backend/app/{api, core, models, schemas, workers,
│               services/{inventory, pricing, forecasting, payments, delivery, checkout}}
├─ backend/{alembic, tests, scripts/seed_history.py}
├─ frontend/src/{pages/shop, pages/admin, components, api}
└─ docker-compose.yml
```

---

## 5. Sơ đồ cơ sở dữ liệu (bản nháp)

```
staff_users(id, email, password_hash, full_name, role[staff|owner], is_active, created_at)

flower_types(id, name, color, reference_cost, vase_life_days, image_url, is_active)
suppliers(id, name, phone, note)

batches(id, flower_type_id, supplier_id, quantity_received, quantity_available,
        cost_per_stem, received_at, expected_expiry_at, freshness_override, status)

inventory_movements(id, batch_id, order_id?, type[IMPORT|RESERVE|RELEASE|SELL|WASTE|ADJUST],
                    quantity, reason, created_by?, created_at)

bouquet_templates(id, name, description, image_url, price, is_active, updated_by, updated_at)
template_items(template_id, flower_type_id, quantity)
template_price_history(id, template_id, old_price, new_price, changed_by, changed_at)

orders(id, code UNIQUE, tracking_token UNIQUE, idempotency_key UNIQUE,
       customer_name, customer_phone, recipient_name?, recipient_phone?,
       delivery_address, delivery_lat, delivery_lng, delivery_distance_km, delivery_fee,
       delivery_slot_day_id, card_message?, note?,
       subtotal, discount_total, total, status, hold_expires_at, created_at)
order_items(id, order_id, template_id, quantity, unit_price_snapshot, discount_pct_snapshot)
order_allocations(id, order_item_id, batch_id, flower_type_id, quantity)   ← kết quả FEFO

payments(id, order_id, provider[mock|vnpay], txn_ref UNIQUE, amount, status, raw_payload, created_at)

urgency_scores(flower_type_id, computed_at, expiring_qty, expected_demand, surplus, discount_pct)
bouquet_templates.discount_locked (bool)            ← mẫu không giảm giá
template_discounts(template_id, current_pct, updated_at)
template_discount_log(id, template_id, old_pct, new_pct, reason_json, created_at)
pricing_rules(id, days_left_max, discount_pct)

delivery_fee_tiers(id, from_km, to_km, fee_per_km)  + settings: base_km, base_fee, max_km,
                                                      holiday_surcharge_pct, free_ship_min_total, free_ship_max_km
delivery_slots(id, start_time, end_time, default_capacity, is_active)
delivery_slot_days(id, slot_id, date, capacity, reserved_count, is_closed)   UNIQUE(slot_id, date)
shop_settings(key, value)   ← tọa độ shop, trần giảm giá, biên lợi nhuận tối thiểu, kill switch, lead time…

holiday_factors(id, name, date, flower_type_id?, template_id?, multiplier)
demand_forecasts(flower_type_id, target_date, predicted_qty, model_version, created_at)
```

---

## 6. Những chỗ "khó" để kể khi phỏng vấn

1. **Chống bán vượt cho cả giỏ hàng nhiều bó:** gộp nhu cầu theo loại hoa, transaction all-or-nothing, khóa theo thứ tự cố định để tránh deadlock; test bắn 50 request đồng thời.
2. **FEFO trên nhiều lô, có xét giờ giao:** không lấy lô sẽ héo trước giờ giao; hủy đơn thì nhả về đúng lô.
3. **Thanh toán an toàn:** chữ ký HMAC-SHA512, IPN idempotent, kiểm tra số tiền, xử lý IPN đến sau khi giữ chỗ đã hết hạn — tất cả test được nhờ mock provider.
4. **Guest checkout an toàn:** link theo dõi bằng token không đoán được, idempotency key chống đặt trùng, rate limit chống dò mã và spam đơn giữ hoa.
5. **Phí ship không giả mạo được:** server tự tính, báo giá có hạn và có chữ ký, có dự phòng khi API bản đồ lỗi, có cache.
6. **Sổ kho bất biến (ledger):** tồn kho luôn tính lại được từ lịch sử → audit + số liệu hao hụt.
7. **Giảm giá tự động nhưng an toàn:** chỉ giảm khi dự báo cho thấy thật sự thừa; có trần, sàn biên lợi nhuận, giới hạn biến động, kill switch và nhật ký lý do.
8. **Sức chứa khung giờ:** giữ chỗ khung giờ và giữ hoa trong cùng một transaction — hai tài nguyên khan hiếm, cùng thành công hoặc cùng thất bại.
9. **Thiết kế có thể thay thế (ports & adapters):** `PaymentProvider`, `DistanceProvider` — đổi mock sang thật không đụng logic nghiệp vụ.

---

## 7. Lộ trình 2 tuần

| Ngày | Việc |
|---|---|
| **1** | Khởi tạo repo, Docker Compose (Postgres, Redis), khung FastAPI, Alembic, CI, auth JWT cho staff/owner |
| **2** | CRUD loại hoa, nhà cung cấp, mẫu bó + công thức + giá admin nhập + lịch sử giá |
| **3** | Nhập lô, sổ kho, ghi hao hụt, API tồn theo lô + độ tươi, cảnh báo biên lợi nhuận |
| **4** | Checkout guest: tính lại giỏ, **FEFO cho cả giỏ + giữ hoa + giữ khung giờ**, idempotency, test đồng thời |
| **5** | **Phí ship**: `DistanceProvider` (Goong + Haversine dự phòng), bảng phí, báo giá có chữ ký, cache; CRUD khung giờ |
| **6** | **Thanh toán mock**: trang thanh toán giả, chữ ký, IPN idempotent; job nhả giữ chỗ; link theo dõi đơn |
| **7** | Script sinh dữ liệu 12 tháng; Celery beat (quét lô hết hạn); rate limit |
| **8** | **B**: điểm gấp, giảm giá mẫu tự động + rào chắn + nhật ký, mục "Tươi nhất hôm nay" |
| **9** | **E**: dự báo, gợi ý nhập hàng, backtest MAPE |
| **10–11** | Frontend khách (mobile-first): danh sách mẫu, giỏ hàng, nhập địa chỉ + bản đồ, thanh toán mock, theo dõi đơn |
| **12** | Frontend quản trị (tối giản): nhập lô, tồn theo lô, mẫu & giá, khung giờ, nhật ký giảm giá, dự báo |
| **13** | Deploy, README, sơ đồ kiến trúc, Swagger |
| **14** | Dự phòng, quay video demo |

> ⚠️ Lịch khá kín sau khi thêm phí ship + giỏ hàng. Nếu trễ, thứ tự hy sinh: (1) phụ phí giờ cao điểm/miễn phí ship, (2) bản đồ ghim vị trí (chỉ giữ ô nhập địa chỉ), (3) giao diện quản trị chỉ dùng Swagger.

**Để giai đoạn sau:** shop 3D, VNPay thật, thay thế hoa thông minh (C), quy trình thợ bó có ảnh xác nhận (F), chấm điểm nhà cung cấp (G), thông báo SMS/Zalo.

---

## 8. Việc bạn cần chuẩn bị trước khi code

1. **Đăng ký Goong** (tự đăng ký, mình không làm hộ được): lấy **API key** (dùng ở backend) và **Maptiles key** (dùng ở frontend). Chưa có key vẫn code được — hệ thống tự dùng Haversine.
2. **Cài sẵn:** Docker Desktop, Python 3.12+, Node.js 20+, Git.
3. **Tọa độ shop mẫu** cho dữ liệu demo: chọn một địa chỉ bất kỳ (vd. một quận ở TP.HCM hoặc Hà Nội).

Không còn câu hỏi thiết kế nào mở. Các chi tiết nhỏ phát sinh khi code sẽ ghi vào nhật ký quyết định ở đầu file.

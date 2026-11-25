"""Sinh dữ liệu demo: mô phỏng N ngày vận hành shop hoa (mặc định 365 ngày tới hôm qua).

Mỗi ngày:
  06:00  nhập lô (thứ 2, thứ 5, và 2 ngày trước dịp lễ lớn) — lượng nhập theo dự kiến có sai số
  07–21h khách đặt hàng: số đơn theo mẫu × thứ trong tuần × hệ số lễ × ngẫu nhiên Poisson;
         hoa lấy theo FEFO; thiếu hoa thì mất đơn (ghi nhận "lost")
  23:30  hoa hỏng ngẫu nhiên theo chất lượng nhà cung cấp; lô hết hạn -> bỏ (ghi hao hụt)

Ghi thẳng vào bảng bằng Core insert (nhanh, giữ đúng các bất biến: tồn = tổng sổ kho, đơn có
phân bổ lô, khung giờ có sức chứa). Cùng `seed` + `end_date` + `now` -> cùng dữ liệu.
Dữ liệu này là đầu vào cho dự báo nhu cầu (ngày 9) — ghi rõ là dữ liệu mô phỏng.
"""

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import slugify
from app.models import (
    Batch,
    BatchStatus,
    BouquetTemplate,
    DeliverySlot,
    DeliverySlotDay,
    FlowerType,
    InventoryMovement,
    MovementType,
    Order,
    OrderAllocation,
    OrderEvent,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
    Supplier,
    TemplateItem,
)
from app.schemas.settings import DeliverySettings
from app.services.delivery_fee import compute_fee
from app.services.maps import haversine_km

VN = ZoneInfo("Asia/Ho_Chi_Minh")
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

BUSINESS_TABLES = [
    "demand_forecasts",
    "template_discount_log",
    "template_discounts",
    "urgency_scores",
    "payments",
    "order_events",
    "order_allocations",
    "order_items",
    "inventory_movements",
    "orders",
    "delivery_slot_days",
    "batches",
    "template_price_history",
    "template_items",
    "bouquet_templates",
    "suppliers",
    "flower_types",
]


class SeedError(Exception):
    pass


# ============================================================ Dữ liệu danh mục
FLOWERS = [  # tên, màu, số ngày tươi, giá vốn tham khảo / cành
    ("Hồng đỏ Đà Lạt", "đỏ", 7, 9_000),
    ("Hồng phấn", "hồng", 7, 9_000),
    ("Hồng trắng", "trắng", 7, 9_500),
    ("Hồng kem", "kem", 7, 9_500),
    ("Tulip Hà Lan", "hồng", 5, 25_000),
    ("Cẩm tú cầu", "xanh", 4, 30_000),
    ("Cúc tana", "trắng", 12, 2_500),
    ("Cúc mẫu đơn", "vàng", 10, 6_000),
    ("Cẩm chướng", "hồng", 12, 5_000),
    ("Baby trắng", "trắng", 10, 3_000),
    ("Hướng dương", "vàng", 6, 12_000),
    ("Lan hồ điệp", "tím", 14, 45_000),
    ("Thạch thảo", "tím", 10, 3_500),
    ("Lá bạch đàn", "xanh", 14, 2_000),
    ("Lá chanh", "xanh", 10, 1_500),
]


@dataclass(frozen=True)
class SupplierSpec:
    name: str
    phone: str
    vase_delta: float  # chênh số ngày tươi so với chuẩn
    cost_factor: float
    daily_spoil: float  # tỷ lệ hỏng mỗi đêm


SUPPLIERS = [
    SupplierSpec("Vườn hoa Đà Lạt Xanh", "0263 3822 111", 0.0, 1.00, 0.010),
    SupplierSpec("HTX Hoa Thái Phiên", "0263 3555 222", -0.5, 0.95, 0.015),
    SupplierSpec("Nhà vườn Sa Đéc", "0277 3861 333", -1.5, 0.85, 0.030),
    SupplierSpec("Hoa nhập khẩu Hà Lan", "028 3930 4444", 1.0, 1.25, 0.008),
]
IMPORTED_FLOWERS = {"Tulip Hà Lan", "Lan hồ điệp"}


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    price: int
    popularity: float
    recipe: dict[str, int]
    description: str
    discount_locked: bool = False


TEMPLATES = [
    TemplateSpec(
        "Đỏ Rực Đam Mê",
        450_000,
        1.3,
        {"Hồng đỏ Đà Lạt": 10, "Baby trắng": 3, "Lá bạch đàn": 4},
        "10 hồng đỏ Đà Lạt cùng baby trắng — món quà kinh điển cho người thương.",
    ),
    TemplateSpec(
        "Pastel Ngọt Ngào",
        380_000,
        1.4,
        {"Hồng phấn": 5, "Cẩm chướng": 3, "Baby trắng": 3, "Lá chanh": 3},
        "Tông hồng pastel dịu dàng, hợp sinh nhật và kỷ niệm.",
    ),
    TemplateSpec(
        "Nắng Hạ",
        320_000,
        0.9,
        {"Hướng dương": 3, "Cúc tana": 5, "Lá chanh": 3},
        "Hướng dương rực rỡ, mang năng lượng tích cực.",
    ),
    TemplateSpec(
        "Tinh Khôi",
        420_000,
        1.0,
        {"Hồng trắng": 7, "Baby trắng": 5, "Lá bạch đàn": 3},
        "Trắng tinh khôi, thanh lịch cho mọi dịp.",
    ),
    TemplateSpec(
        "Tulip Hà Lan",
        650_000,
        0.6,
        {"Tulip Hà Lan": 10, "Lá bạch đàn": 3},
        "10 tulip nhập khẩu Hà Lan.",
    ),
    TemplateSpec(
        "Cẩm Tú Mộng Mơ",
        550_000,
        0.7,
        {"Cẩm tú cầu": 2, "Hồng kem": 4, "Thạch thảo": 3},
        "Cẩm tú cầu xanh mát phối hồng kem.",
    ),
    TemplateSpec(
        "Mẹ Hiền",
        350_000,
        0.9,
        {"Cẩm chướng": 6, "Cúc mẫu đơn": 4, "Baby trắng": 3, "Lá chanh": 3},
        "Cẩm chướng — loài hoa dành tặng mẹ.",
    ),
    TemplateSpec(
        "Thanh Lịch",
        890_000,
        0.35,
        {"Lan hồ điệp": 3, "Hồng trắng": 5, "Lá bạch đàn": 3},
        "Lan hồ điệp sang trọng cho khai trương, đối tác.",
    ),
    TemplateSpec(
        "Mini Xinh",
        180_000,
        1.6,
        {"Hồng phấn": 3, "Baby trắng": 2, "Lá chanh": 2},
        "Bó nhỏ xinh xắn, giá dễ thương.",
    ),
    TemplateSpec(
        "Tím Thủy Chung",
        300_000,
        0.7,
        {"Thạch thảo": 5, "Cẩm chướng": 5, "Baby trắng": 3},
        "Sắc tím thủy chung.",
    ),
    TemplateSpec(
        "Tốt Nghiệp Rạng Rỡ",
        420_000,
        0.5,
        {"Hướng dương": 2, "Hồng kem": 5, "Baby trắng": 3, "Lá bạch đàn": 3},
        "Chúc mừng tốt nghiệp.",
    ),
    TemplateSpec(
        "Trăm Năm Hạnh Phúc",
        990_000,
        0.25,
        {"Hồng đỏ Đà Lạt": 20, "Baby trắng": 5, "Lá bạch đàn": 5},
        "20 hồng đỏ — mẫu cao cấp, không áp giảm giá.",
        discount_locked=True,
    ),
]

ADDRESSES = [  # (địa chỉ, lat, lng) quanh trung tâm TP.HCM
    ("Lê Lợi, Bến Nghé, Quận 1", 10.7769, 106.7009),
    ("Võ Văn Tần, Quận 3", 10.7835, 106.6870),
    ("Ba Tháng Hai, Quận 10", 10.7730, 106.6680),
    ("Xô Viết Nghệ Tĩnh, Bình Thạnh", 10.8040, 106.7120),
    ("Phan Xích Long, Phú Nhuận", 10.7990, 106.6800),
    ("Nguyễn Thị Thập, Quận 7", 10.7340, 106.7220),
    ("Khánh Hội, Quận 4", 10.7600, 106.7040),
    ("Thảo Điền, TP. Thủ Đức", 10.8040, 106.7370),
    ("Cộng Hòa, Tân Bình", 10.8010, 106.6520),
    ("Quang Trung, Gò Vấp", 10.8380, 106.6650),
    ("Trần Hưng Đạo, Quận 5", 10.7560, 106.6680),
]
SURNAMES = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng"]
MIDDLE = ["Văn", "Thị", "Minh", "Ngọc", "Thanh", "Hoàng", "Gia", "Bảo"]
GIVEN = [
    "An",
    "Bình",
    "Châu",
    "Dũng",
    "Giang",
    "Hà",
    "Khoa",
    "Linh",
    "My",
    "Nam",
    "Phúc",
    "Quân",
    "Trang",
    "Tú",
    "Vy",
    "Yến",
]

BASE_LINES_PER_DAY = 22  # tổng số dòng (bó) mỗi ngày thường, trước hệ số thứ & lễ
WEEKDAY_FACTOR = [0.85, 0.85, 0.9, 0.95, 1.15, 1.4, 1.3]  # thứ 2 … chủ nhật
LUNAR_NEW_YEAR = {2025: date(2025, 1, 29), 2026: date(2026, 2, 17), 2027: date(2027, 2, 6)}


# ============================================================ Mùa vụ & ngày lễ
def _mothers_day(year: int) -> date:
    may1 = date(year, 5, 1)
    first_sunday = may1 + timedelta(days=(6 - may1.weekday()) % 7)
    return first_sunday + timedelta(days=7)


def _holiday_table(d: date) -> dict[str, float] | None:
    """Hệ số theo mẫu cho ngày lễ (khóa "*" = các mẫu còn lại)."""
    md = d.strftime("%m-%d")
    if md == "02-14":
        return {
            "Đỏ Rực Đam Mê": 8,
            "Trăm Năm Hạnh Phúc": 7,
            "Pastel Ngọt Ngào": 3.5,
            "Tulip Hà Lan": 3,
            "Mini Xinh": 3,
            "*": 1.8,
        }
    if md == "03-08":
        return {"Thanh Lịch": 4, "*": 3.5}
    if md == "10-20":
        return {"*": 3.5}
    if md == "11-20":
        return {
            "Tím Thủy Chung": 4.5,
            "Pastel Ngọt Ngào": 3.5,
            "Tinh Khôi": 3.5,
            "Mẹ Hiền": 3,
            "*": 2.2,
        }
    if md == "12-24":
        return {"Đỏ Rực Đam Mê": 2.2, "Trăm Năm Hạnh Phúc": 2, "*": 1.3}
    if d == _mothers_day(d.year):
        return {"Mẹ Hiền": 4.5, "Cẩm Tú Mộng Mơ": 2.5, "*": 1.6}
    return None


def _lookup(table: dict[str, float], name: str) -> float:
    return table.get(name, table["*"])


def demand_multiplier(template_name: str, d: date) -> float:
    m = 1.0
    if table := _holiday_table(d):
        m *= _lookup(table, template_name)
    elif table := _holiday_table(d + timedelta(days=1)):
        m *= 1 + (_lookup(table, template_name) - 1) * 0.4  # đặt trước một ngày
    if template_name == "Tốt Nghiệp Rạng Rỡ" and (5, 20) <= (d.month, d.day) <= (6, 30):
        m *= 3
    if template_name == "Nắng Hạ" and (5, 20) <= (d.month, d.day) <= (6, 30):
        m *= 1.8
    tet = LUNAR_NEW_YEAR.get(d.year) or LUNAR_NEW_YEAR.get(d.year + 1)
    if tet:
        delta = (d - tet).days
        if -7 <= delta < 0:
            m *= 1.6  # mua hoa trước Tết
        elif 0 <= delta <= 3:
            m *= 0.3  # mùng 1–4 vắng khách
    return m


def expected_lines(spec: TemplateSpec, d: date) -> float:
    share = spec.popularity / sum(t.popularity for t in TEMPLATES)
    return (
        BASE_LINES_PER_DAY * share * WEEKDAY_FACTOR[d.weekday()] * demand_multiplier(spec.name, d)
    )


def cost_spike(flower: str, d: date) -> float:
    md = (d.month, d.day)
    if flower.startswith("Hồng") and (2, 11) <= md <= (2, 14):
        return 1.8
    for hm, hd in ((3, 8), (10, 20), (11, 20)):
        target = date(d.year, hm, hd)
        if 0 <= (target - d).days <= 3:
            return 1.3
    return 1.0


# ============================================================ Mô phỏng
@dataclass
class SimBatch:
    id: int
    flower_id: int
    supplier: int  # index trong SUPPLIERS
    supplier_id: int
    received: int
    available: int
    cost: int
    received_at: datetime
    expiry: datetime
    status: BatchStatus = BatchStatus.ACTIVE


@dataclass
class SeedReport:
    start_date: date
    end_date: date
    orders: int = 0
    lost_orders: int = 0
    bouquets: int = 0
    revenue: int = 0
    batches: int = 0
    stems_imported: int = 0
    stems_wasted: int = 0
    orders_by_day: dict[date, int] = field(default_factory=dict)

    @property
    def waste_pct(self) -> float:
        return round(100 * self.stems_wasted / self.stems_imported, 2) if self.stems_imported else 0


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 30:  # xấp xỉ chuẩn cho λ lớn
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _vn(d: date, h: int, m: int = 0) -> datetime:
    return datetime.combine(d, time(h, m), tzinfo=VN).astimezone(UTC)


async def _ensure_empty(session: AsyncSession, reset: bool) -> None:
    if reset:
        await session.execute(
            text(f"TRUNCATE {', '.join(BUSINESS_TABLES)} RESTART IDENTITY CASCADE")
        )
        await session.commit()
        return
    for table in BUSINESS_TABLES:
        if await session.scalar(text(f"SELECT EXISTS (SELECT 1 FROM {table})")):  # noqa: S608
            raise SeedError(f"Table '{table}' is not empty — run with --reset to wipe demo data")


async def _fix_sequences(session: AsyncSession) -> None:
    for table in BUSINESS_TABLES:
        if table in ("template_items", "template_discounts", "urgency_scores", "demand_forecasts"):
            continue
        await session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "  # noqa: S608
                f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
                f"(SELECT COUNT(*) > 0 FROM {table}))"
            )
        )


async def _bulk(session: AsyncSession, model, rows: list[dict], chunk: int = 4000) -> None:
    for i in range(0, len(rows), chunk):
        await session.execute(insert(model.__table__), rows[i : i + chunk])


async def seed_demo(
    session: AsyncSession,
    *,
    days: int = 365,
    end_date: date | None = None,
    seed: int = 42,
    reset: bool = False,
    now: datetime | None = None,
) -> SeedReport:
    now = now or datetime.now(UTC)
    end_date = end_date or (now.astimezone(VN).date() - timedelta(days=1))
    start_date = end_date - timedelta(days=days - 1)
    rng = random.Random(seed)  # noqa: S311 — mô phỏng cần tái lập được, không dùng cho bảo mật
    report = SeedReport(start_date, end_date)
    settings = DeliverySettings()

    await _ensure_empty(session, reset)

    # ---------------- Danh mục (ít dòng -> dùng ORM cho gọn)
    flowers = {
        name: FlowerType(name=name, color=color, vase_life_days=vase, reference_cost=cost)
        for name, color, vase, cost in FLOWERS
    }
    suppliers = [Supplier(name=s.name, phone=s.phone) for s in SUPPLIERS]
    session.add_all([*flowers.values(), *suppliers])
    await session.flush()
    templates = []
    for spec in TEMPLATES:
        t = BouquetTemplate(
            name=spec.name,
            slug=slugify(spec.name),
            description=spec.description,
            price=spec.price,
            discount_locked=spec.discount_locked,
            items=[
                TemplateItem(flower_type_id=flowers[f].id, quantity=q)
                for f, q in spec.recipe.items()
            ],
        )
        templates.append((spec, t))
    session.add_all([t for _, t in templates])
    await session.flush()

    slots = (
        await session.scalars(
            select(DeliverySlot)
            .where(DeliverySlot.is_active.is_(True))
            .order_by(DeliverySlot.start_time)
        )
    ).all()
    if not slots:
        for s, e in [(8, 10), (10, 12), (13, 15), (15, 17), (17, 19)]:
            session.add(DeliverySlot(start_time=time(s), end_time=time(e), default_capacity=6))
        await session.flush()
        slots = (
            await session.scalars(select(DeliverySlot).order_by(DeliverySlot.start_time))
        ).all()

    flower_id = {name: f.id for name, f in flowers.items()}
    vase_of = {name: vase for name, _, vase, _ in FLOWERS}
    cost_of = {name: cost for name, _, _, cost in FLOWERS}
    recipe_ids = {
        spec.name: {flower_id[f]: q for f, q in spec.recipe.items()} for spec, _ in templates
    }

    # ---------------- Bộ đếm id + bộ đệm dòng
    ids: dict[str, int] = defaultdict(int)

    def next_id(table: str) -> int:
        ids[table] += 1
        return ids[table]

    rows: dict[str, list[dict]] = defaultdict(list)
    batches: list[SimBatch] = []
    slot_day_ids: dict[tuple[int, date], int] = {}
    slot_day_count: dict[int, int] = defaultdict(int)
    slot_day_rows: dict[int, dict] = {}
    used_codes: set[str] = set()

    def movement(
        batch: SimBatch,
        type_: MovementType,
        qty: int,
        at: datetime,
        reason: str | None = None,
        order_id: int | None = None,
    ) -> None:
        rows["movements"].append(
            {
                "id": next_id("movements"),
                "batch_id": batch.id,
                "order_id": order_id,
                "type": type_,
                "quantity": qty,
                "reason": reason,
                "created_at": at,
            }
        )

    def expected_stems(fid: int, d: date) -> float:
        return sum(
            expected_lines(spec, d) * 1.12 * recipe_ids[spec.name].get(fid, 0)
            for spec, _ in templates
        )

    def big_holiday_soon(d: date) -> bool:
        return any(
            (_holiday_table(d + timedelta(days=k)) or {}).get("*", 1) >= 1.6
            or "Đỏ Rực Đam Mê" in (_holiday_table(d + timedelta(days=k)) or {})
            for k in (1, 2)
        )

    def do_import(d: date) -> None:
        horizon = 4 if d.weekday() == 3 else 3
        at = _vn(d, 6)
        for name in flower_id:
            fid = flower_id[name]
            need = sum(expected_stems(fid, d + timedelta(days=h)) for h in range(horizon + 1))
            need *= rng.uniform(0.9, 1.25)
            usable_until = _vn(d + timedelta(days=2), 12)
            usable = sum(
                b.available
                for b in batches
                if b.flower_id == fid and b.status == BatchStatus.ACTIVE and b.expiry > usable_until
            )
            qty = math.ceil(max(0.0, need * 1.15 - usable) / 10) * 10  # nhập theo bó 10 cành
            if qty <= 0:
                continue
            if name in IMPORTED_FLOWERS:
                sup = rng.choices([3, 0], weights=[3, 1])[0]
            else:
                sup = rng.choices([0, 1, 2], weights=[3, 2, 2])[0]
            spec = SUPPLIERS[sup]
            vase = max(2.0, vase_of[name] + spec.vase_delta + rng.uniform(-0.5, 0.5))
            cost = round(cost_of[name] * spec.cost_factor * cost_spike(name, d) / 100) * 100
            b = SimBatch(
                next_id("batches"),
                fid,
                sup,
                suppliers[sup].id,
                qty,
                0,
                cost,
                at,
                at + timedelta(days=vase),
            )
            batches.append(b)
            report.batches += 1
            report.stems_imported += qty
            b.available = qty
            movement(b, MovementType.IMPORT, qty, at)

    def slot_day_id(slot: DeliverySlot, d: date) -> int:
        key = (slot.id, d)
        if key not in slot_day_ids:
            sid = next_id("slot_days")
            slot_day_ids[key] = sid
            slot_day_rows[sid] = {
                "id": sid,
                "slot_id": slot.id,
                "date": d,
                "capacity": slot.default_capacity,
                "reserved_count": 0,
                "is_closed": False,
            }
        return slot_day_ids[key]

    def new_code(created: datetime) -> str:
        day = created.astimezone(VN).strftime("%y%m%d")
        while True:
            code = f"MF-{day}-" + "".join(rng.choice(CODE_ALPHABET) for _ in range(4))
            if code not in used_codes:
                used_codes.add(code)
                return code

    def place_order(d: date, created: datetime, lines: list[tuple[TemplateSpec, int]]) -> None:
        # Chọn khung giao: cùng ngày nếu kịp (≥ 2h) và tung đồng xu, không thì ngày mai
        same_day = [
            s
            for s in slots
            if _vn(d, s.start_time.hour, s.start_time.minute) >= created + timedelta(hours=2)
        ]
        if same_day and rng.random() < 0.6:
            day, slot = d, rng.choice(same_day)
        else:
            day, slot = d + timedelta(days=1), rng.choice(slots)
        starts = _vn(day, slot.start_time.hour, slot.start_time.minute)
        ends = _vn(day, slot.end_time.hour, slot.end_time.minute)

        demand: dict[int, int] = defaultdict(int)
        for spec, qty in lines:
            for fid, q in recipe_ids[spec.name].items():
                demand[fid] += q * qty
        pools = {
            fid: sorted(
                (
                    b
                    for b in batches
                    if b.flower_id == fid
                    and b.status == BatchStatus.ACTIVE
                    and b.available > 0
                    and b.expiry > ends
                ),
                key=lambda b: (b.expiry, b.id),
            )
            for fid in demand
        }
        if any(sum(b.available for b in pools[fid]) < need for fid, need in demand.items()):
            report.lost_orders += 1
            return

        order_id = next_id("orders")
        code = new_code(created)
        subtotal = sum(spec.price * qty for spec, qty in lines)
        addr, lat, lng = rng.choice(ADDRESSES)
        lat += rng.uniform(-0.004, 0.004)
        lng += rng.uniform(-0.004, 0.004)
        km = haversine_km(settings.shop_lat, settings.shop_lng, lat, lng) * 1.3
        fee = compute_fee(km, settings=settings, delivery_date=day, subtotal=subtotal)
        delivered = ends < now
        status = OrderStatus.COMPLETED if delivered else OrderStatus.PAID
        sd_id = slot_day_id(slot, day)
        slot_day_count[sd_id] += 1
        name = f"{rng.choice(SURNAMES)} {rng.choice(MIDDLE)} {rng.choice(GIVEN)}"
        rows["orders"].append(
            {
                "id": order_id,
                "code": code,
                "tracking_token": f"seed-{rng.getrandbits(160):040x}",
                "idempotency_key": f"seed-{order_id}",
                "request_fingerprint": "seed",
                "status": status,
                "customer_name": name,
                "customer_phone": f"09{rng.randrange(10**8):08d}",
                "recipient_name": None,
                "recipient_phone": None,
                "delivery_address": f"{rng.randint(1, 300)} {addr}, TP.HCM",
                "delivery_lat": lat,
                "delivery_lng": lng,
                "delivery_distance_km": fee.distance_km,
                "delivery_slot_day_id": sd_id,
                "delivery_starts_at": starts,
                "delivery_ends_at": ends,
                "card_message": None,
                "note": None,
                "subtotal": subtotal,
                "discount_total": 0,
                "delivery_fee": fee.total,
                "total": subtotal + fee.total,
                "hold_expires_at": None,
                "created_at": created,
                "updated_at": created,
            }
        )
        paid_at = created + timedelta(minutes=rng.randint(2, 6))
        rows["payments"].append(
            {
                "id": next_id("payments"),
                "order_id": order_id,
                "provider": "mock",
                "txn_ref": f"{code}-SEED",
                "amount": subtotal + fee.total,
                "status": PaymentStatus.SUCCEEDED,
                "response_code": "00",
                "gateway_txn_no": f"{rng.randrange(10**8):08d}",
                "needs_refund": False,
                "paid_at": paid_at,
                "created_at": created,
                "updated_at": paid_at,
            }
        )
        timeline = [
            (None, OrderStatus.PENDING_PAYMENT, "customer", created),
            (OrderStatus.PENDING_PAYMENT, OrderStatus.PAID, "payment", paid_at),
        ]
        if delivered:
            done = starts + timedelta(minutes=rng.randint(30, 100))
            timeline += [
                (OrderStatus.PAID, OrderStatus.PREPARING, "staff", starts - timedelta(minutes=70)),
                (OrderStatus.PREPARING, OrderStatus.DELIVERING, "staff", starts),
                (OrderStatus.DELIVERING, OrderStatus.COMPLETED, "staff", done),
            ]
        for frm, to, actor, at in timeline:
            rows["events"].append(
                {
                    "id": next_id("events"),
                    "order_id": order_id,
                    "from_status": frm,
                    "to_status": to,
                    "actor": actor,
                    "actor_id": None,
                    "note": None,
                    "created_at": at,
                }
            )

        taken: dict[int, int] = defaultdict(int)
        batch_by_id: dict[int, SimBatch] = {}
        for spec, qty in lines:
            item_id = next_id("items")
            rows["items"].append(
                {
                    "id": item_id,
                    "order_id": order_id,
                    "template_id": tpl_id[spec.name],
                    "template_name": spec.name,
                    "quantity": qty,
                    "unit_price": spec.price,
                    "discount_pct": 0,
                    "line_total": spec.price * qty,
                }
            )
            for fid, q in recipe_ids[spec.name].items():
                need = q * qty
                for b in pools[fid]:
                    if not need:
                        break
                    take = min(need, b.available)
                    if take == 0:
                        continue
                    b.available -= take
                    need -= take
                    taken[b.id] += take
                    batch_by_id[b.id] = b
                    rows["allocations"].append(
                        {
                            "id": next_id("allocations"),
                            "order_item_id": item_id,
                            "batch_id": b.id,
                            "flower_type_id": fid,
                            "quantity": take,
                        }
                    )
        for bid, qty in sorted(taken.items()):
            b = batch_by_id[bid]
            movement(b, MovementType.RESERVE, -qty, created, f"Order {code}", order_id)
            if b.available == 0:
                b.status = BatchStatus.DEPLETED
        report.orders += 1
        report.bouquets += sum(q for _, q in lines)
        report.revenue += subtotal
        report.orders_by_day[d] = report.orders_by_day.get(d, 0) + 1

    def end_of_day(d: date) -> None:
        at = _vn(d, 23, 30)
        cutoff = _vn(d + timedelta(days=1), 7)  # sáng mai không bán được nữa -> bỏ
        for b in batches:
            if b.status != BatchStatus.ACTIVE or b.available == 0:
                continue
            if b.expiry <= cutoff:
                movement(b, MovementType.WASTE, -b.available, at, "Quá hạn — bỏ (giả lập)")
                report.stems_wasted += b.available
                b.available = 0
                b.status = BatchStatus.DISCARDED
                continue
            p = SUPPLIERS[b.supplier].daily_spoil * rng.uniform(0.5, 1.5)
            spoiled = min(b.available, round(b.available * p))
            if spoiled:
                movement(b, MovementType.WASTE, -spoiled, at, "Héo/gãy cành (giả lập)")
                report.stems_wasted += spoiled
                b.available -= spoiled
                if b.available == 0:
                    b.status = BatchStatus.DEPLETED

    tpl_id = {spec.name: t.id for spec, t in templates}

    # ---------------- Vòng lặp từng ngày
    d = start_date
    while d <= end_date:
        if d == start_date or d.weekday() in (0, 3) or big_holiday_soon(d):
            do_import(d)
        lines: list[tuple[TemplateSpec, int]] = []
        for spec, _ in templates:
            for _ in range(_poisson(rng, expected_lines(spec, d))):
                lines.append((spec, rng.choices([1, 2, 3], weights=[90, 8, 2])[0]))
        rng.shuffle(lines)
        groups: list[list[tuple[TemplateSpec, int]]] = []
        while lines:
            size = rng.choices([1, 2, 3], weights=[80, 17, 3])[0]
            group, seen = [], set()
            while lines and len(group) < size:
                spec, qty = lines.pop()
                if spec.name in seen:  # mỗi mẫu chỉ một dòng trong đơn
                    lines.insert(0, (spec, qty))
                    break
                seen.add(spec.name)
                group.append((spec, qty))
            groups.append(group)
        created_times = sorted(
            _vn(d, 7) + timedelta(minutes=rng.randint(0, 14 * 60)) for _ in groups
        )
        for created, group in zip(created_times, groups, strict=True):
            place_order(d, created, group)
        end_of_day(d)
        d += timedelta(days=1)

    # ---------------- Ghi xuống DB
    for sid, count in slot_day_count.items():
        r = slot_day_rows[sid]
        r["reserved_count"] = count
        r["capacity"] = max(r["capacity"], count)  # chủ shop đã tăng sức chứa dịp đông
    await _bulk(
        session,
        Batch,
        [
            {
                "id": b.id,
                "flower_type_id": b.flower_id,
                "supplier_id": b.supplier_id,
                "quantity_received": b.received,
                "quantity_available": b.available,
                "cost_per_stem": b.cost,
                "received_at": b.received_at,
                "expected_expiry_at": b.expiry,
                "freshness_override": None,
                "status": b.status,
                "note": None,
                "created_by_id": None,
                "created_at": b.received_at,
                "updated_at": b.received_at,
            }
            for b in batches
        ],
    )
    await _bulk(session, DeliverySlotDay, list(slot_day_rows.values()))
    await _bulk(session, Order, rows["orders"])
    await _bulk(session, OrderItem, rows["items"])
    await _bulk(session, OrderAllocation, rows["allocations"])
    await _bulk(session, InventoryMovement, rows["movements"])
    await _bulk(session, OrderEvent, rows["events"])
    await _bulk(session, Payment, rows["payments"])
    await _fix_sequences(session)
    await session.commit()

    total_batches = await session.scalar(select(func.count()).select_from(Batch))
    assert total_batches == report.batches  # noqa: S101 — tự kiểm tra
    return report

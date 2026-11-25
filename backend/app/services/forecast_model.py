"""Mô hình dự báo nhu cầu v1 — thuần Python, không đụng DB (dễ test, dễ backtest).

    dự_báo(hoa, ngày) = nền(hoa, thứ trong tuần) × hệ_số_lễ(hoa, ngày)
    nền = trung bình số cành bán vào CÙNG THỨ trong `weeks` tuần gần nhất, sau khi đã chia cho
          hệ số lễ của từng ngày đó ("khử mùa vụ") — để một ngày 14/2 trong lịch sử không làm
          phồng dự báo của các thứ Bảy thường.

Đơn giản, giải thích được từng con số, và đủ tốt để làm baseline cho mô hình ML sau này.
Đo bằng backtest cuộn (rolling origin) so với 2 cách ngây thơ.
"""

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta

MODEL_VERSION = "weekday-mean-8w+holiday-v1"
DEFAULT_WEEKS = 8
MIN_POINTS = 3  # ít hơn số điểm này cùng thứ -> dùng TB mọi ngày gần đây

History = Mapping[date, float]  # ngày -> số cành bán (đã điền 0 cho ngày không bán)
FactorFn = Callable[[date], tuple[float, str | None]]


# ============================================================ Hệ số lễ
@dataclass(frozen=True)
class HolidayRule:
    name: str
    multiplier: float
    month_day: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    flower_type_id: int | None = None

    def matches(self, d: date) -> bool:
        if self.month_day is not None:
            return d.strftime("%m-%d") == self.month_day
        return self.start_date <= d <= self.end_date  # type: ignore[operator]


def holiday_factor(
    rules: Iterable[HolidayRule], d: date, flower_type_id: int
) -> tuple[float, str | None]:
    """Quy tắc riêng của loại hoa thắng quy tắc chung; cùng cấp thì lấy hệ số lớn nhất."""
    matching = [r for r in rules if r.matches(d)]
    specific = [r for r in matching if r.flower_type_id == flower_type_id]
    general = [r for r in matching if r.flower_type_id is None]
    pool = specific or general
    if not pool:
        return 1.0, None
    best = max(pool, key=lambda r: r.multiplier)
    return best.multiplier, best.name


def factor_fn(rules: Iterable[HolidayRule], flower_type_id: int) -> FactorFn:
    rules = list(rules)
    return lambda d: holiday_factor(rules, d, flower_type_id)


# ============================================================ Dự báo
@dataclass(frozen=True)
class Forecast:
    predicted: float
    base: float
    multiplier: float
    holiday: str | None
    points: int  # số ngày lịch sử đã dùng


def weekday_base(
    history: History, origin: date, weekday: int, factor: FactorFn, weeks: int = DEFAULT_WEEKS
) -> tuple[float, int]:
    """Nền cho một thứ, chỉ dùng dữ liệu TRƯỚC `origin` (không nhìn trộm tương lai)."""
    last = origin - timedelta(days=1)
    back = (last.weekday() - weekday) % 7
    days = [last - timedelta(days=back + 7 * k) for k in range(weeks)]
    points = [history[d] / factor(d)[0] for d in days if d in history]
    if len(points) >= MIN_POINTS:
        return sum(points) / len(points), len(points)
    # Shop mới / ít dữ liệu: TB khử mùa vụ của mọi ngày trong `weeks` tuần qua
    recent = [last - timedelta(days=k) for k in range(7 * weeks)]
    pts = [history[d] / factor(d)[0] for d in recent if d in history]
    return (sum(pts) / len(pts), len(pts)) if pts else (0.0, 0)


def forecast_day(
    history: History, origin: date, target: date, factor: FactorFn, weeks: int = DEFAULT_WEEKS
) -> Forecast:
    base, points = weekday_base(history, origin, target.weekday(), factor, weeks)
    mult, name = factor(target)
    return Forecast(round(base * mult, 3), round(base, 3), mult, name, points)


# ============================================================ Nhập hàng
def restock_quantity(
    forecast_total: float, usable_stock: int, safety_pct: int, bundle: int = 10
) -> int:
    """cần_nhập = dự báo × (1 + an toàn) − tồn còn dùng được, làm tròn LÊN theo bó."""
    need = forecast_total * (100 + safety_pct) / 100 - usable_stock
    return 0 if need <= 0 else math.ceil(need / bundle) * bundle


# ============================================================ Đo sai số
def wape(pairs: Iterable[tuple[float, float]]) -> float | None:
    """Weighted APE = Σ|thực − dự báo| / Σ thực. Ổn định với số bán nhỏ / có ngày bán 0
    (MAPE chia cho từng ngày nên nổ tung khi một ngày chỉ bán 1–2 cành)."""
    pairs = list(pairs)
    total = sum(a for a, _ in pairs)
    return round(100 * sum(abs(a - f) for a, f in pairs) / total, 2) if total else None


def mape(pairs: Iterable[tuple[float, float]]) -> float | None:
    """MAPE cổ điển, bỏ các ngày thực tế = 0 (không xác định)."""
    errs = [abs(a - f) / a for a, f in pairs if a > 0]
    return round(100 * sum(errs) / len(errs), 2) if errs else None


@dataclass
class Score:
    wape: float | None
    mape: float | None
    points: int


@dataclass
class BacktestResult:
    origins: int
    horizon: int
    model: Score
    naive_last_week: Score  # = cùng thứ tuần trước
    moving_avg_14: Score  # = TB 14 ngày (cách ngày 8 đang dùng)
    per_flower: dict[int, Score] = field(default_factory=dict)


def _score(pairs: list[tuple[float, float]]) -> Score:
    return Score(wape(pairs), mape(pairs), len(pairs))


def backtest(
    histories: Mapping[int, History],
    rules: Iterable[HolidayRule],
    origins: Iterable[date],
    horizon: int = 7,
    weeks: int = DEFAULT_WEEKS,
) -> BacktestResult:
    """Rolling origin: đứng ở mỗi ngày `o`, chỉ biết dữ liệu trước `o`, dự báo o … o+horizon−1
    rồi so với thực tế. Mọi phương pháp chấm trên cùng tập điểm."""
    rules = list(rules)
    origins = list(origins)
    model, naive, ma = [], [], []
    per_flower: dict[int, list[tuple[float, float]]] = {}
    for fid, hist in histories.items():
        fn = factor_fn(rules, fid)
        mine = per_flower.setdefault(fid, [])
        for o in origins:
            past14 = [hist.get(o - timedelta(days=k), 0.0) for k in range(1, 15)]
            avg14 = sum(past14) / 14
            for h in range(horizon):
                target = o + timedelta(days=h)
                if target not in hist:
                    continue
                actual = hist[target]
                pred = forecast_day(hist, o, target, fn, weeks).predicted
                model.append((actual, pred))
                mine.append((actual, pred))
                naive.append((actual, hist.get(target - timedelta(days=7 * (1 + h // 7)), 0.0)))
                ma.append((actual, avg14))
    return BacktestResult(
        origins=len(origins),
        horizon=horizon,
        model=_score(model),
        naive_last_week=_score(naive),
        moving_avg_14=_score(ma),
        per_flower={fid: _score(p) for fid, p in per_flower.items()},
    )

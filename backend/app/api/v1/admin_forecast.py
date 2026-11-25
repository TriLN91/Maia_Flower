import re
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Annotated, Self

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.api.deps import CurrentOwner, CurrentStaff, SessionDep
from app.core.errors import NotFoundError
from app.models import DemandForecast, FlowerType, HolidayFactor
from app.services import forecasting
from app.services.inventory import utcnow

router = APIRouter(prefix="/admin")


# ---------------- Schemas
class ForecastDayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_date: date
    predicted_qty: float
    base_qty: float
    multiplier: float
    holiday: str | None


class FlowerForecastOut(BaseModel):
    flower_type_id: int
    name: str
    total: float
    days: list[ForecastDayOut]


class RestockOut(BaseModel):
    flower_type_id: int
    name: str
    cover_days: int
    forecast_total: float
    usable_stock: int
    safety_pct: int
    suggested_qty: int
    est_unit_cost: int
    est_cost: int
    holidays: list[str]


class ScoreOut(BaseModel):
    wape: float | None = Field(description="Σ|thực−dự báo| / Σ thực (%) — chỉ số chính")
    mape: float | None = Field(description="TB |thực−dự báo|/thực trên ngày có bán (%)")
    points: int


class BacktestOut(BaseModel):
    origins: int
    horizon: int
    model: ScoreOut
    naive_last_week: ScoreOut
    moving_avg_14: ScoreOut
    improvement_vs_moving_avg_pct: float | None
    per_flower: list[dict]


def _mm_dd(v: str | None) -> str | None:
    if v is not None and not re.fullmatch(r"(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", v):
        raise ValueError("month_day must be MM-DD")
    return v


class HolidayIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    multiplier: Annotated[float, Field(gt=0, le=50)]
    month_day: str | None = Field(default=None, description="Lặp hằng năm, vd. 02-14")
    start_date: date | None = None
    end_date: date | None = None
    flower_type_id: int | None = Field(default=None, description="Trống = mọi loại hoa")

    @model_validator(mode="after")
    def _xor(self) -> Self:
        _mm_dd(self.month_day)
        has_range = self.start_date is not None or self.end_date is not None
        if (self.month_day is None) == (not has_range):
            raise ValueError("Provide either month_day or start_date+end_date")
        if has_range and (
            self.start_date is None or self.end_date is None or self.end_date < self.start_date
        ):
            raise ValueError("start_date and end_date are both required, end ≥ start")
        return self


class HolidayOut(HolidayIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


# ---------------- Dự báo
@router.get("/forecast", response_model=list[FlowerForecastOut], tags=["admin: forecast"])
async def get_forecast(
    session: SessionDep,
    _: CurrentStaff,
    flower_type_id: int | None = None,
    days: Annotated[int, Query(ge=1, le=14)] = 14,
) -> list[FlowerForecastOut]:
    """Dự báo số cành bán mỗi ngày (đã lưu bởi job đêm / nút tính lại)."""
    today = forecasting.local_today(utcnow())
    stmt = (
        select(DemandForecast, FlowerType.name)
        .join(FlowerType, FlowerType.id == DemandForecast.flower_type_id)
        .where(
            DemandForecast.target_date >= today,
            DemandForecast.target_date < today + timedelta(days=days),
        )
        .order_by(FlowerType.name, DemandForecast.target_date)
    )
    if flower_type_id is not None:
        stmt = stmt.where(DemandForecast.flower_type_id == flower_type_id)
    grouped: dict[int, FlowerForecastOut] = {}
    for f, name in (await session.execute(stmt)).all():
        g = grouped.setdefault(
            f.flower_type_id,
            FlowerForecastOut(flower_type_id=f.flower_type_id, name=name, total=0, days=[]),
        )
        g.days.append(ForecastDayOut.model_validate(f))
        g.total = round(g.total + f.predicted_qty, 2)
    return sorted(grouped.values(), key=lambda g: -g.total)


@router.post("/forecast/recompute", tags=["admin: forecast"])
async def recompute_forecast(session: SessionDep, _: CurrentOwner) -> dict[str, int]:
    return {"rows": await forecasting.recompute_forecasts(session, utcnow())}


@router.get("/restock-suggestions", response_model=list[RestockOut], tags=["admin: forecast"])
async def restock(
    session: SessionDep,
    _: CurrentStaff,
    import_date: Annotated[date | None, Query(alias="date")] = None,
    cover_days: Annotated[int, Query(ge=1, le=14)] = 4,
    safety_pct: Annotated[int, Query(ge=0, le=100)] = 15,
) -> list[RestockOut]:
    """Nên nhập bao nhiêu cành mỗi loại vào sáng `date` (mặc định ngày mai)."""
    now = utcnow()
    day = import_date or forecasting.local_today(now) + timedelta(days=1)
    lines = await forecasting.restock_suggestions(session, now, day, cover_days, safety_pct)
    return [RestockOut(**line.__dict__) for line in lines]


@router.get("/forecast/backtest", response_model=BacktestOut, tags=["admin: forecast"])
async def backtest(
    session: SessionDep,
    _: CurrentOwner,
    days: Annotated[int, Query(ge=7, le=180)] = 56,
    horizon: Annotated[int, Query(ge=1, le=14)] = 7,
) -> BacktestOut:
    """Đo sai số mô hình trên dữ liệu quá khứ (rolling origin), so với 2 cách ngây thơ."""
    r = await forecasting.run_backtest(session, utcnow(), days, horizon)
    names = dict((await session.execute(select(FlowerType.id, FlowerType.name))).all())
    improvement = None
    if r.model.wape is not None and r.moving_avg_14.wape:
        improvement = round(100 * (1 - r.model.wape / r.moving_avg_14.wape), 1)
    return BacktestOut(
        origins=r.origins,
        horizon=r.horizon,
        model=ScoreOut(**r.model.__dict__),
        naive_last_week=ScoreOut(**r.naive_last_week.__dict__),
        moving_avg_14=ScoreOut(**r.moving_avg_14.__dict__),
        improvement_vs_moving_avg_pct=improvement,
        per_flower=sorted(
            (
                {"flower_type_id": fid, "name": names.get(fid), **s.__dict__}
                for fid, s in r.per_flower.items()
                if s.wape is not None
            ),
            key=lambda x: x["wape"],
        ),
    )


# ---------------- Hệ số lễ
@router.get("/holiday-factors", response_model=list[HolidayOut], tags=["admin: forecast"])
async def list_holidays(session: SessionDep, _: CurrentStaff) -> Sequence[HolidayFactor]:
    return (
        await session.scalars(
            select(HolidayFactor).order_by(
                HolidayFactor.month_day.nulls_last(), HolidayFactor.start_date, HolidayFactor.id
            )
        )
    ).all()


@router.post(
    "/holiday-factors",
    response_model=HolidayOut,
    status_code=status.HTTP_201_CREATED,
    tags=["admin: forecast"],
)
async def create_holiday(session: SessionDep, _: CurrentOwner, body: HolidayIn) -> HolidayFactor:
    if (
        body.flower_type_id is not None
        and await session.get(FlowerType, body.flower_type_id) is None
    ):
        raise NotFoundError("Flower type not found")
    row = HolidayFactor(**body.model_dump())
    session.add(row)
    await session.commit()
    return row


@router.put("/holiday-factors/{holiday_id}", response_model=HolidayOut, tags=["admin: forecast"])
async def update_holiday(
    session: SessionDep, _: CurrentOwner, holiday_id: int, body: HolidayIn
) -> HolidayFactor:
    row = await session.get(HolidayFactor, holiday_id)
    if row is None:
        raise NotFoundError("Holiday factor not found")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    await session.commit()
    return row


@router.delete(
    "/holiday-factors/{holiday_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["admin: forecast"],
)
async def delete_holiday(session: SessionDep, _: CurrentOwner, holiday_id: int) -> None:
    row = await session.get(HolidayFactor, holiday_id)
    if row is None:
        raise NotFoundError("Holiday factor not found")
    await session.delete(row)
    await session.commit()

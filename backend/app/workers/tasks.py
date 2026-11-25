import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.services.forecasting import recompute_forecasts
from app.services.inventory import mark_expired_batches, utcnow
from app.services.order_workflow import expire_overdue_orders
from app.services.payments.service import handle_ipn
from app.services.pricing import recompute
from app.workers.celery_app import celery_app


def run_in_session[T](fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Celery task là hàm đồng bộ: mỗi lần chạy tạo event loop + engine riêng (NullPool),
    vì kết nối asyncpg gắn với event loop đã tạo ra nó."""

    async def main() -> T:
        engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(main())


@celery_app.task(name="app.workers.tasks.expire_unpaid_orders")
def expire_unpaid_orders() -> int:
    return run_in_session(lambda s: expire_overdue_orders(s, utcnow()))


@celery_app.task(
    name="app.workers.tasks.deliver_mock_ipn",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=5,
)
def deliver_mock_ipn(params: dict[str, str]) -> str:
    """Cổng giả lập gửi IPN trễ (nút "IPN đến trễ 2 phút")."""
    return run_in_session(lambda s: handle_ipn(s, params, utcnow())).RspCode


@celery_app.task(name="app.workers.tasks.mark_expired_batches")
def mark_expired_batches_task() -> int:
    return run_in_session(lambda s: mark_expired_batches(s, utcnow()))


@celery_app.task(name="app.workers.tasks.recompute_pricing")
def recompute_pricing() -> int:
    return run_in_session(lambda s: recompute(s, utcnow())).templates_changed


@celery_app.task(name="app.workers.tasks.recompute_forecasts")
def recompute_forecasts_task() -> int:
    return run_in_session(lambda s: recompute_forecasts(s, utcnow()))

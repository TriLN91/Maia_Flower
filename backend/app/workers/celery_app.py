"""Celery: job nền + lịch chạy định kỳ.

    celery -A app.workers.celery_app worker --loglevel=info      # worker
    celery -A app.workers.celery_app beat --loglevel=info        # bộ hẹn giờ
(Dev chạy gộp bằng `worker --beat` trong docker-compose; production nên tách 2 tiến trình
và chỉ chạy MỘT beat.)
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

celery_app = Celery("maia_flower", broker=get_settings().redis_url, include=["app.workers.tasks"])
celery_app.conf.update(
    timezone="UTC",
    task_acks_late=True,  # worker chết giữa chừng -> task được chạy lại
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "expire-unpaid-orders": {
            "task": "app.workers.tasks.expire_unpaid_orders",
            "schedule": 60.0,  # mỗi phút: đơn quá 15' chưa trả tiền sẽ được nhả trong ≤ 1'
        },
        "mark-expired-batches": {
            "task": "app.workers.tasks.mark_expired_batches",
            "schedule": crontab(hour=17, minute=30),  # 17:30 UTC = 00:30 giờ Việt Nam
        },
    },
)

#!/bin/sh
# Khởi động bản production (Render). Thứ tự: migration -> (demo) seed -> (tùy chọn) Celery -> API.
set -e

alembic upgrade head

if [ "$DEMO_MODE" = "true" ]; then
  # Lần đầu: sinh dữ liệu 12 tháng + tài khoản demo. Các lần sau: bỏ qua.
  python -m app.cli seed-demo --if-empty --demo-accounts || echo "demo seed skipped"
fi

if [ "$RUN_WORKER_IN_WEB" = "true" ]; then
  # Gói miễn phí không có background worker riêng -> chạy Celery (worker + beat) cạnh API.
  # Đánh đổi: dịch vụ miễn phí "ngủ" sau 15 phút không có truy cập thì job cũng tạm dừng.
  celery -A app.workers.celery_app worker --beat --concurrency=1 --loglevel=info \
    --schedule=/tmp/celerybeat-schedule &
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips="*"

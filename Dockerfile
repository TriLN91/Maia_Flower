# Image production cho API (Render). Web là Static Site riêng (xem render.yaml) — image này
# không còn build frontend. Dev dùng backend/Dockerfile + docker-compose (hot reload).
#
# Vẫn hỗ trợ chế độ "một dịch vụ" (API phục vụ luôn web) nếu đặt FRONTEND_DIST_DIR trỏ tới một
# bản build Vite có sẵn — xem docs/DEPLOY.md.

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production

WORKDIR /app
# Cài dependency trước để tận dụng cache layer
COPY backend/pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install . && rm -rf app build *.egg-info
COPY backend/ ./
RUN pip install --no-deps . && chmod +x scripts/start.sh

RUN useradd --create-home --uid 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/v1/health',timeout=4)"
CMD ["scripts/start.sh"]

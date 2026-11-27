# Image production: MỘT dịch vụ phục vụ cả API lẫn web (cùng origin -> không cần CORS).
# Dev dùng backend/Dockerfile + docker-compose (hot reload); file này dùng để deploy (Render).

# ---------- 1) Build frontend ----------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- 2) Backend ----------
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production \
    FRONTEND_DIST_DIR=/app/static

WORKDIR /app
# Cài dependency trước để tận dụng cache layer
COPY backend/pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install . && rm -rf app build *.egg-info
COPY backend/ ./
RUN pip install --no-deps . && chmod +x scripts/start.sh
COPY --from=web /web/dist /app/static

RUN useradd --create-home --uid 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/v1/health',timeout=4)"
CMD ["scripts/start.sh"]

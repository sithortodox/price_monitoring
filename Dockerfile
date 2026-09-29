# syntax=docker/dockerfile:1
# Собирать из корня репозитория:  docker build -t site-monitoring .
# Перед сборкой нужен фронтенд:    cd frontend && npm ci && npm run build

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        fonts-liberation \
        fonts-noto-cjk \
        libnss3 \
        libatk-bridge2.0-0 \
        libgtk-3-0 \
        libgbm1 \
        libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt

# Chromium для сайтов на JavaScript (autoopt, truckdrive).
# Если загрузка не удалась — остальные 9 сайтов работают как обычно.
RUN python -m playwright install --with-deps chromium || \
    echo "WARN: playwright chromium не установлен — браузерные парсеры будут недоступны"

COPY backend /app/backend
# Собранный SPA (см. frontend/package.json → npm run build)
COPY frontend/dist /app/frontend/dist

WORKDIR /app/backend

ENV FRONTEND_DIST=/app/frontend/dist \
    AUTO_CREATE_TABLES=true \
    DATABASE_URL=postgresql+psycopg2://monitor:monitor@db:5432/site_monitoring

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

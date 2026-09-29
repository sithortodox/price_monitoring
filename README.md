# Мониторинг цен и спроса запчастей конкурентов

Ежедневный автоматический сбор цен, остатков и данных о спросе по 11 сайтам-конкурентам
(список и правила разбора — по ТЗ), с аналитикой и выгрузкой в Excel.

* FastAPI + SQLAlchemy + PostgreSQL 16 — API, парсеры, аналитика
* React (Vite) — одностраничный интерфейс
* Playwright/Chromium — сайты, отдающие контент по JS (autoopt, truckdrive)
* APScheduler — ежедневный запуск в 21:00 МСК
* Docker Compose — один контейнер приложения + PostgreSQL

## Быстрый старт (Ubuntu, Docker)

```bash
git clone git@github.com:sithortodox/site-monitoring.git
cd site-monitoring

# фронтенд собирается до сборки образа (COPY frontend/dist)
cd frontend && npm install && npm run build && cd ..

docker compose up -d --build
docker compose ps          # дождаться app: healthy
curl -s http://localhost:8000/api/health
```

Интерфейс: <http://localhost:8000>. Порт меняется переменной `APP_PORT` в `.env`.

При старте автоматически выполняются миграции (`alembic upgrade head`),
создаются таблицы и сидируются 11 конкурентов.

## Интерфейс

* **Dashboard** — сводка за день: итоги, рейтинги A/B/C/D/NEW, топ спроса, состояние сайтов
* **Конкуренты** — включение/выключение, ручной сбор, настройка и проверка прокси
* **Товары** — поиск по артикулу/OEM, история цен и остатков по каждому конкуренту
* **Топ** — спрос, продажи, конкурентоспособность
* **Экспорт** — Excel за день или период, 4 листа (Сводка, Аналитика спроса, Цены конкурентов, Остатки и изменения)

Ручной запуск полного цикла:

```bash
curl -X POST http://localhost:8000/api/run -H 'Content-Type: application/json' -d '{}'
```

## Расписание

Ежедневный сбор в **21:00 МСК** (`SCHEDULE_HOUR`, `SCHEDULE_MINUTE`, `TIMEZONE`).
Запуск идёт тем же кодом, что и ручной (`jobs.start_run`), поэтому в интерфейсе виден
ход выполнения, а параллельный ручной запуск отклоняется.

```bash
docker logs -f site-monitoring-app | grep -E "scheduler|daily"
```

## Прокси

Для сайтов, блокирующих IP (например, truckdrive.ru):

* **через интерфейс:** Конкуренты → кнопка «Прокси» → ввести URL → «Проверить» → «Сохранить»;
* **глобально:** переменная `PROXY_URL` в `.env`.

Поддерживаются `host:port`, `http://user:pass@host:port`, `socks5://host:port`.
Прокси одного сайта (`competitors.config.proxy_url`) перекрывает глобальный.

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `APP_PORT` | 8000 | порт веб-интерфейса |
| `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` / `TIMEZONE` | 21 / 0 / Europe/Moscow | время ежедневного сбора |
| `HTTP_DELAY_SEC` | 1.0 | пауза между запросами к одному сайту |
| `MAX_PAGES_PER_SITE` | 100 | предохранитель от бесконечных каталогов |
| `PROXY_URL` | — | общий прокси (пусто = напрямую) |
| `SCHEDULER_ENABLED` | true | включить планировщик |
| `BROWSER_ENABLED` | true | Playwright-парсеры (autoopt, truckdrive) |

Полный список — в `.env.example`.

## Разработка

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # или свой backend/.env для локального запуска

python -m pytest tests -q       # 80 тестов
python -m ruff check .          # линтер
alembic upgrade head            # миграции
uvicorn app.main:app --reload   # http://127.0.0.1:8000

cd ../frontend
npm install && npm run dev      # Vite dev-сервер
```

Тесты используют SQLite во временном каталоге и не требуют PostgreSQL.

## Структура

```
backend/app/parsers/       парсеры 11 сайтов (base + sites/*), нормализация, fetcher
backend/app/services/      runner (сбор), snapshot, analytics, report, excel_export
backend/app/api/           маршруты REST API
backend/alembic/           миграции схемы
backend/tests/             pytest + HTML-фикстуры сайтов
frontend/src/              React SPA (pages, api, components)
Dockerfile, docker-compose.yml
```

## Бэкап базы

```bash
docker exec site-monitoring-db pg_dump -U monitor site_monitoring | gzip > backup_$(date +%F).sql.gz
# восстановление:
gunzip -c backup_2026-09-29.sql.gz | docker exec -i site-monitoring-db psql -U monitor -d site_monitoring
```

## Известные ограничения

* **truckdrive.ru** при интенсивных прогонах блокирует IP — используйте прокси.
* **autopiter.ru** отдаёт цены деталей только авторизованным пользователям:
  анонимный обход завершается с понятным предупреждением (partial).
* Числовые остатки берутся там, где их публикует сайт (autoopt, sh-parts, transek,
  amrparts, relines, aac86); для dcc/glavmeh/stugs доступно только наличие.
* Продажи/восполнения считаются со второго дня наблюдений (нужны два снимка подряд).

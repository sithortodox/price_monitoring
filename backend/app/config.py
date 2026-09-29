from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Мониторинг запчастей конкурентов"
    debug: bool = False

    database_url: str = "postgresql+psycopg2://monitor:monitor@localhost:5432/site_monitoring"

    # Планировщик
    scheduler_enabled: bool = True
    schedule_hour: int = 21  # 21:00 МСК — в интервале 20:00–23:00 по ТЗ
    schedule_minute: int = 0
    timezone: str = "Europe/Moscow"

    # Парсинг
    http_timeout: float = 25.0
    http_delay_sec: float = 1.0  # пауза между запросами к одному сайту
    http_retries: int = 2
    max_pages_per_site: int = 100  # защита от бесконечных каталогов (truckdrive обходит ~40 листовых групп)
    # Прокси для всех сайтов (пусто = напрямую); для одного сайта — competitors.config.proxy_url
    proxy_url: str | None = None
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    # Playwright (для сайтов на JS)
    browser_enabled: bool = True
    browser_executable_path: str | None = None
    browser_headless: bool = True

    # Аналитика
    history_days_required_for_rating: int = 7
    report_top_n: int = 50
    vanished_grace_days: int = 3

    # Хранение
    retention_months: int = 0  # 0 = без ограничения срока (п.25 ТЗ)
    auto_create_tables: bool = True  # create_all + seed при старте (для MVP)

    # Excel
    export_dir: Path = BASE_DIR / "exports"

    # Собранный фронтенд (SPA раздаётся бэкендом)
    frontend_dist: Path = BASE_DIR.parent / "frontend" / "dist"

    # Авторизация (простой пароль для веб-интерфейса; пусто = выключено)
    auth_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

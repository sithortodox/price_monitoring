from __future__ import annotations

import logging
import time
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings

log = logging.getLogger("scheduler")

# страховка от «вечного» ожидания: цикл нормально занимает 15–30 минут
_MAX_WAIT_SEC = 6 * 3600
_POLL_SEC = 5


def daily_job() -> dict | None:
    """Ежедневный полный цикл: парсинг → снимки → аналитика → отчёт (п.20 ТЗ).

    Запуск идёт через jobs.start_run — тем же путём, что и ручной запуск из API,
    чтобы статус в /api/run/status и защита от параллельных запусков работали
    одинаково для расписания и для оператора.
    """
    from .jobs import job_status, start_run  # локальный импорт — jobs не знает о scheduler

    status = start_run(trigger="auto")
    if not status.get("started"):
        log.warning("daily run skipped: %s", status.get("reason"))
        return None

    deadline = time.monotonic() + _MAX_WAIT_SEC
    while job_status()["running"] and time.monotonic() < deadline:
        time.sleep(_POLL_SEC)

    state = job_status()
    if state.get("error"):
        log.error("daily run failed: %s", state["error"])
    elif state.get("running"):
        log.error("daily run did not finish in %s hours", _MAX_WAIT_SEC // 3600)
    else:
        result = state.get("result") or {}
        log.info("daily run finished: %s", result.get("snapshots"))
    return state.get("result")


def create_scheduler() -> BackgroundScheduler | None:
    if not settings.scheduler_enabled:
        log.info("scheduler disabled by config")
        return None

    tz = ZoneInfo(settings.timezone)
    scheduler = BackgroundScheduler(timezone=tz)
    scheduler.add_job(
        daily_job,
        trigger=CronTrigger(
            hour=settings.schedule_hour,
            minute=settings.schedule_minute,
            timezone=tz,
        ),
        id="daily_monitoring",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
        name=f"Ежедневный мониторинг ({settings.schedule_hour:02d}:{settings.schedule_minute:02d} {settings.timezone})",
    )
    return scheduler

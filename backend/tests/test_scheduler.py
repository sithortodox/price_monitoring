from __future__ import annotations

from app import jobs, scheduler


def test_daily_job_starts_run_with_auto_trigger(monkeypatch):
    """Расписанный запуск должен идти через jobs — иначе не виден в /api/run/status."""
    seen: dict[str, object] = {}

    def fake_start(competitor_ids=None, trigger="manual"):
        seen["trigger"] = trigger
        seen["competitor_ids"] = competitor_ids
        return {"started": True}

    monkeypatch.setattr(jobs, "start_run", fake_start)
    monkeypatch.setattr(
        jobs,
        "job_status",
        lambda: {"running": False, "error": None, "result": {"snapshots": {"written": 3}}},
    )

    result = scheduler.daily_job()

    assert seen["trigger"] == "auto"
    assert seen["competitor_ids"] is None
    assert result == {"snapshots": {"written": 3}}


def test_daily_job_skips_when_another_run_is_active(monkeypatch):
    monkeypatch.setattr(
        jobs, "start_run", lambda competitor_ids=None, trigger="manual": {"started": False, "reason": "already_running"}
    )
    polled = {"n": 0}

    def fake_status():
        polled["n"] += 1
        return {"running": False, "error": None, "result": None}

    monkeypatch.setattr(jobs, "job_status", fake_status)

    assert scheduler.daily_job() is None
    assert polled["n"] == 0  # ожидание не начиналось — запуск отклонён


def test_scheduler_is_disabled_in_tests():
    from app.scheduler import create_scheduler

    assert create_scheduler() is None


def test_scheduler_registers_daily_job_with_configured_time(monkeypatch):
    from app.config import settings
    from app.scheduler import create_scheduler

    monkeypatch.setattr(settings, "scheduler_enabled", True)
    built = create_scheduler()
    assert built is not None
    job = built.get_job("daily_monitoring")
    assert job is not None
    assert f"{settings.schedule_hour:02d}:{settings.schedule_minute:02d}" in job.name
    assert settings.timezone in job.name
    # планировщик не запускался — ресурсов не занято, shutdown не нужен

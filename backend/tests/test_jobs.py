from __future__ import annotations

import time

from app import jobs


def test_run_lock_rejects_parallel_start(monkeypatch):
    def fake_run_all(db, trigger="manual", competitor_ids=None):
        time.sleep(0.3)
        return {"ok": True}

    monkeypatch.setattr(jobs, "run_all", fake_run_all)

    first = jobs.start_run([], trigger="manual")
    second = jobs.start_run([], trigger="manual")

    assert first["started"] is True
    assert second["started"] is False
    assert second["reason"] == "already_running"

    deadline = time.time() + 5
    while jobs.job_status()["running"] and time.time() < deadline:
        time.sleep(0.05)

    status = jobs.job_status()
    assert status["running"] is False
    assert status["result"] == {"ok": True}
    assert status["error"] is None
    assert status["finished_at"] is not None

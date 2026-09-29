from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from .db import session_scope
from .services.runner import run_all

log = logging.getLogger("jobs")

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "trigger": None,
    "started_at": None,
    "finished_at": None,
    "result": None,
    "error": None,
}


def job_status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def start_run(competitor_ids: list[int] | None = None, trigger: str = "manual") -> dict[str, Any]:
    """Зускает полный цикл в фоне; повторный запуск, пока идёт текущий, отклоняется."""
    with _lock:
        if _state["running"]:
            return {"started": False, "reason": "already_running", "status": dict(_state)}
        _state.update(
            running=True,
            trigger=trigger,
            started_at=datetime.now().isoformat(timespec="seconds"),
            finished_at=None,
            result=None,
            error=None,
        )

    def _worker() -> None:
        db = session_scope()
        try:
            result = run_all(db, trigger=trigger, competitor_ids=competitor_ids)
            with _lock:
                _state["result"] = result
        except Exception as exc:
            log.exception("background run failed")
            with _lock:
                _state["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            db.close()
            with _lock:
                _state["running"] = False
                _state["finished_at"] = datetime.now().isoformat(timespec="seconds")

    threading.Thread(target=_worker, name="monitoring-run", daemon=True).start()
    return {"started": True, "status": job_status()}

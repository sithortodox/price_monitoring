from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import update

from .api.routes import router as api_router
from .config import settings
from .db import engine, session_scope
from .models import RUN_ERROR, RUN_RUNNING, Base, ParserRun
from .scheduler import create_scheduler
from .seed import reset_urls_from_registry, seed_competitors
from .services.analytics import ensure_index_weights

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("app")



@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    scheduler = create_scheduler()
    if scheduler:
        scheduler.start()
        log.info(
            "scheduler started: daily at %s:%02d (%s)",
            settings.schedule_hour,
            settings.schedule_minute,
            settings.timezone,
        )
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
    engine.dispose()


def init_database() -> None:
    """Создаёт таблицы (если нужно), сидит конкурентов и веса индекса."""
    if settings.auto_create_tables:
        Base.metadata.create_all(engine)
    db = session_scope()
    try:
        created = seed_competitors(db)
        filled = reset_urls_from_registry(db)
        ensure_index_weights(db)
        # запуски, "висящие" в running после перезапуска процесса, помечаем ошибкой
        stale = db.execute(
            update(ParserRun)
            .where(ParserRun.status == RUN_RUNNING)
            .values(
                status=RUN_ERROR,
                error_message="прервано перезапуском приложения",
                finished_at=datetime.now(),
            )
        ).rowcount
        if stale:
            log.warning("marked %d stale running parser runs as error", stale)
            db.commit()
        if created or filled:
            log.info("seeded competitors: created=%s urls_filled=%s", created, filled)
    finally:
        db.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Ежедневный мониторинг цен, остатков и спроса запчастей конкурентов",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.get("/api/time")
    def server_time() -> dict[str, str]:
        return {"now": time.strftime("%Y-%m-%d %H:%M:%S")}

    dist = settings.frontend_dist
    if dist.is_dir():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        index_file = dist / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse:
            candidate = dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index_file)
    else:
        log.warning("frontend dist not found at %s — UI будет доступен после сборки", dist)

    return app


app = create_app()

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    AV_UNKNOWN,
    RUN_ERROR,
    RUN_PARTIAL,
    RUN_RUNNING,
    RUN_SUCCESS,
    Competitor,
    Offer,
    ParserRun,
    clip,
)
from ..parsers.base import RawOffer
from ..parsers.fetcher import BrowserFetcher, Fetcher, normalize_proxy
from ..parsers.registry import get_parser_class
from .analytics import recompute_stats
from .matcher import ProductMatcher
from .report import build_daily_report
from .snapshot import TodayValues, write_snapshots

log = logging.getLogger("services.runner")


def upsert_offers(db: Session, competitor: Competitor, raw_offers: list[RawOffer], day: date) -> TodayValues:
    """Превращает сырые позиции в товары и предложения с актуальными значениями."""
    matcher = ProductMatcher(db)
    values: TodayValues = {}
    for raw in raw_offers:
        if not raw.url or not raw.title:
            continue
        product = matcher.match(raw)
        offer = db.execute(
            select(Offer).where(
                Offer.product_id == product.id,
                Offer.competitor_id == competitor.id,
                Offer.url == raw.url[:1000],
            )
        ).scalar_one_or_none()
        if offer is None:
            offer = Offer(
                product_id=product.id,
                competitor_id=competitor.id,
                url=raw.url[:1000],
            )
            db.add(offer)
            db.flush()

        offer.seller_article = clip(raw.seller_article, 200)
        offer.external_id = clip(raw.external_id, 100)
        offer.category = clip(raw.category, 300) or offer.category
        offer.active = True
        offer.seen_on = day
        offer.last_seen_at = datetime.now()

        values[offer.id] = {
            "price": raw.price,
            "old_price": raw.old_price,
            "qty": raw.qty,
            "qty_text": clip(raw.qty_text, 200),
            "availability": raw.availability or AV_UNKNOWN,
            "status_text": clip(raw.status_text, 200),
            "warehouse": clip(raw.warehouse, 200),
            "delivery_time": clip(raw.delivery_time, 120),
        }
    db.flush()
    return values


def run_competitor(db: Session, competitor: Competitor, trigger: str = "auto") -> tuple[ParserRun, TodayValues]:
    """Запускает парсинг одного сайта и сохраняет результат (п.24 ТЗ)."""
    run = ParserRun(competitor_id=competitor.id, trigger=trigger, status=RUN_RUNNING)
    db.add(run)
    db.commit()

    started = time.monotonic()
    today = date.today()
    fetcher: Fetcher | None = None
    browser: BrowserFetcher | None = None
    try:
        parser_cls = get_parser_class(competitor.parser_key)
        delay = float(competitor.config.get("delay", parser_cls.delay_sec or settings.http_delay_sec) or 1.0)
        proxy = normalize_proxy(competitor.config.get("proxy_url")) or normalize_proxy(settings.proxy_url)
        fetcher = Fetcher(delay=delay, proxy=proxy)
        if parser_cls.use_browser and settings.browser_enabled:
            browser = BrowserFetcher(delay=delay, proxy=proxy)
        parser = parser_cls(fetcher=fetcher, browser=browser)
        result = parser.parse(competitor, max_pages=settings.max_pages_per_site)

        values = upsert_offers(db, competitor, result.offers, today)
        run.pages_fetched = fetcher.stats.pages + (browser.stats.pages if browser else 0)
        run.items_found = len(result.offers)
        run.offers_written = len(values)
        run.errors_count = fetcher.stats.errors + (browser.stats.errors if browser else 0)
        run.spec_version = parser_cls.spec_version

        if result.offers and (result.errors or run.errors_count):
            run.status = RUN_PARTIAL
            run.error_message = _join(result.errors, fetcher, browser)
        elif result.offers:
            run.status = RUN_SUCCESS
            run.error_message = _join(result.errors, fetcher, browser) or None
        elif result.warnings and not result.errors:
            run.status = RUN_PARTIAL
            run.error_message = "; ".join(result.warnings)
        else:
            run.status = RUN_ERROR
            run.error_message = _join(result.errors, fetcher, browser) or "Парсер не вернул данных"
    except Exception as exc:
        # сначала откатываем сломанную транзакцию, иначе сохранение статуса упадёт
        db.rollback()
        log.exception("competitor %s failed", competitor.name)
        run = db.get(ParserRun, run.id) or run
        run.status = RUN_ERROR
        run.error_message = f"{type(exc).__name__}: {exc}"
        values = {}
    finally:
        run.duration_ms = int((time.monotonic() - started) * 1000)
        run.finished_at = datetime.now()
        if fetcher:
            fetcher.close()
        if browser:
            browser.close()

    db.commit()
    return run, values


def _join(errors: list[str], fetcher: Fetcher | None, browser: BrowserFetcher | None) -> str:
    parts = list(errors)
    if fetcher:
        parts.extend(fetcher.stats.error_messages[:5])
    if browser:
        parts.extend(browser.stats.error_messages[:5])
    return "; ".join(dict.fromkeys(parts))[:2000]


def run_all(
    db: Session,
    trigger: str = "manual",
    competitor_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Полный цикл: парсинг → снимки → аналитика → отчёт (п.3, 20 ТЗ)."""
    day = date.today()
    query = select(Competitor).where(Competitor.enabled.is_(True)).order_by(Competitor.sort_order)
    if competitor_ids:
        query = query.where(Competitor.id.in_(competitor_ids))
    competitors = list(db.execute(query).scalars())

    runs: list[ParserRun] = []
    merged: TodayValues = {}
    for competitor in competitors:
        run, values = run_competitor(db, competitor, trigger=trigger)
        runs.append(run)
        merged.update(values)
        log.info(
            "competitor=%s status=%s items=%s errors=%s",
            competitor.name,
            run.status,
            run.items_found,
            run.errors_count,
        )

    scope_ids = [c.id for c in competitors]
    snapshot_stats = write_snapshots(db, day, merged, scope_competitor_ids=scope_ids)
    analytics_stats = recompute_stats(db, day)
    report = build_daily_report(db, day)
    db.commit()

    return {
        "day": day.isoformat(),
        "competitors": len(competitors),
        "runs": [
            {
                "id": r.id,
                "competitor_id": r.competitor_id,
                "status": r.status,
                "items": r.items_found,
                "pages": r.pages_fetched,
                "errors": r.errors_count,
                "message": r.error_message,
                "duration_ms": r.duration_ms,
            }
            for r in runs
        ],
        "snapshots": snapshot_stats,
        "analytics": analytics_stats,
        "report": report,
    }

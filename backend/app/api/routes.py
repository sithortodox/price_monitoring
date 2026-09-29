from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Text, func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..jobs import job_status, start_run
from ..models import (
    Competitor,
    DailyReport,
    IndexWeight,
    Offer,
    ParserRun,
    Product,
    ProductDaily,
    ProductStats,
    StockSnapshot,
)
from ..parsers.fetcher import normalize_proxy
from ..parsers.registry import available_parsers
from ..services.analytics import ensure_index_weights
from .schemas import (
    CompetitorOut,
    CompetitorPatch,
    HealthOut,
    IndexWeightIn,
    IndexWeightOut,
    OfferOut,
    ParserInfo,
    ProductDetail,
    ProductListItem,
    ProductPage,
    RunOut,
    RunStartIn,
    SeriesPoint,
    TopItem,
)

router = APIRouter(prefix="/api")

SERIES_DAYS = 180
DISCLAIMER = "Предполагаемые продажи рассчитаны по снижению остатков и не являются фактическими."


# ---------------------------------------------------------------- служебное
@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    try:
        db.execute(select(func.count(Competitor.id)))
        database = "ok"
    except Exception as exc:
        database = f"error: {exc}"
    return HealthOut(
        status="ok",
        app=settings.app_name,
        database=database,
        time=datetime.now().isoformat(timespec="seconds"),
    )


@router.get("/parsers", response_model=list[ParserInfo])
def parsers() -> list[ParserInfo]:
    return [ParserInfo(**p) for p in available_parsers()]


# ---------------------------------------------------------------- конкуренты
@router.get("/competitors", response_model=list[CompetitorOut])
def list_competitors(db: Session = Depends(get_db)) -> list[CompetitorOut]:
    return [_competitor_out(db, c) for c in db.execute(select(Competitor).order_by(Competitor.sort_order)).scalars()]


def _competitor_out(db: Session, competitor: Competitor) -> CompetitorOut:
    day = date.today()
    offers_total = (
        db.execute(select(func.count(Offer.id)).where(Offer.competitor_id == competitor.id)).scalar()
        or 0
    )
    offers_today = (
        db.execute(
            select(func.count(Offer.id)).where(
                Offer.competitor_id == competitor.id, Offer.seen_on == day
            )
        ).scalar()
        or 0
    )
    item = CompetitorOut.model_validate(competitor)
    item.offers_total = int(offers_total)
    item.offers_today = int(offers_today)
    return item


@router.patch("/competitors/{competitor_id}", response_model=CompetitorOut)
def patch_competitor(
    competitor_id: int, payload: CompetitorPatch, db: Session = Depends(get_db)
) -> CompetitorOut:
    competitor = db.get(Competitor, competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Конкурент не найден")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(competitor, key, value)
    db.commit()
    return _competitor_out(db, competitor)


@router.post("/competitors/{competitor_id}/run")
def run_competitor_endpoint(competitor_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    if db.get(Competitor, competitor_id) is None:
        raise HTTPException(status_code=404, detail="Конкурент не найден")
    return start_run([competitor_id], trigger="manual")


# ---------------------------------------------------------------- запуски
def _mask_proxy(url: str | None) -> str | None:
    """Пароль в URL прокси не отдаём наружу."""
    if not url:
        return None
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    if not parts.username and not parts.password:
        return url
    host = parts.hostname or ""
    if parts.port:
        host += f":{parts.port}"
    user = f"{parts.username}:" if parts.username else ""
    return urlunsplit((parts.scheme, f"{user}***@{host}", parts.path, parts.query, parts.fragment))


@router.post("/competitors/{competitor_id}/proxy-check")
def proxy_check(competitor_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Проверка доступности сайта через настроенный прокси (кнопка в интерфейсе)."""
    competitor = db.get(Competitor, competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Конкурент не найден")

    site_proxy = normalize_proxy((competitor.config or {}).get("proxy_url"))
    proxy = site_proxy or normalize_proxy(settings.proxy_url)
    source = "site" if site_proxy else ("global" if proxy else "none")

    started = time.monotonic()
    try:
        with httpx.Client(
            proxy=proxy,
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
        ) as client:
            response = client.get(competitor.base_url)
        return {
            "ok": response.status_code < 400,
            "source": source,
            "proxy": _mask_proxy(proxy),
            "status": response.status_code,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "source": source,
            "proxy": _mask_proxy(proxy),
            "status": None,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "error": f"{type(exc).__name__}: {exc}",
        }


@router.post("/run")
def run_manual(payload: RunStartIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    return start_run(payload.competitor_ids, trigger="manual")


@router.get("/run/status")
def run_status() -> dict[str, Any]:
    return job_status()


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    limit: int = Query(default=50, ge=1, le=500),
    competitor_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[RunOut]:
    query = select(ParserRun).order_by(ParserRun.started_at.desc()).limit(limit)
    if competitor_id:
        query = query.where(ParserRun.competitor_id == competitor_id)
    names = {c.id: c.name for c in db.execute(select(Competitor)).scalars()}
    runs = db.execute(query).scalars()
    return [
        RunOut(
            id=run.id,
            competitor_id=run.competitor_id,
            competitor_name=names.get(run.competitor_id),
            trigger=run.trigger,
            status=run.status,
            started_at=run.started_at.isoformat() if run.started_at else None,
            finished_at=run.finished_at.isoformat() if run.finished_at else None,
            pages_fetched=run.pages_fetched,
            items_found=run.items_found,
            offers_written=run.offers_written,
            errors_count=run.errors_count,
            error_message=run.error_message,
            duration_ms=run.duration_ms,
        )
        for run in runs
    ]


# ---------------------------------------------------------------- товары
@router.get("/products", response_model=ProductPage)
def list_products(
    q: str | None = None,
    rating: str | None = None,
    competitor_id: int | None = None,
    sort: str = Query(default="index", pattern="^(index|sales30|sales7|title|price|competitors)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ProductPage:
    query = select(Product, ProductStats).join(
        ProductStats, ProductStats.product_id == Product.id
    )

    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Product.title.ilike(pattern),
                Product.oem.ilike(pattern),
                Product.article.ilike(pattern),
                Product.brand.ilike(pattern),
                Product.alt_numbers.cast(Text).ilike(pattern),
            )
        )
    if rating:
        query = query.where(ProductStats.rating == rating)
    if competitor_id:
        query = query.where(
            Product.id.in_(select(Offer.product_id).where(Offer.competitor_id == competitor_id))
        )

    total = db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar() or 0

    order = {
        "index": ProductStats.index_score.desc(),
        "sales30": ProductStats.sales_30.desc(),
        "sales7": ProductStats.sales_7.desc(),
        "title": Product.title.asc(),
        "price": ProductStats.min_price.asc().nulls_last(),
        "competitors": ProductStats.competitors_count.desc(),
    }[sort]
    rows = db.execute(
        query.order_by(order, Product.id).offset((page - 1) * page_size).limit(page_size)
    ).all()

    qty_today = dict(
        db.execute(
            select(StockSnapshot.product_id, func.sum(StockSnapshot.qty))
            .where(StockSnapshot.snapshot_date == date.today(), StockSnapshot.qty.is_not(None))
            .group_by(StockSnapshot.product_id)
        ).all()
    )
    items = [
        ProductListItem(
            id=p.id,
            title=p.title,
            brand=p.brand,
            oem=p.oem or p.article,
            category=p.category,
            rating=s.rating,
            index_score=float(s.index_score or 0),
            sales_7=s.sales_7,
            sales_14=s.sales_14,
            sales_30=s.sales_30,
            sales_90=s.sales_90,
            frequency_pct=float(s.frequency_pct or 0),
            days_observed=s.days_observed,
            competitors_count=s.competitors_count,
            in_stock_competitors=s.in_stock_competitors,
            min_price=float(s.min_price) if s.min_price is not None else None,
            median_price=float(s.median_price) if s.median_price is not None else None,
            max_price=float(s.max_price) if s.max_price is not None else None,
            price_delta=float(s.price_delta) if s.price_delta is not None else None,
            qty_total=int(qty_today.get(p.id) or 0),
        )
        for p, s in rows
    ]
    return ProductPage(
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, -(-total // page_size)),
        items=items,
    )


@router.get("/products/{product_id}", response_model=ProductDetail)
def product_detail(product_id: int, db: Session = Depends(get_db)) -> ProductDetail:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")

    names = {c.id: c.name for c in db.execute(select(Competitor)).scalars()}
    offers = db.execute(
        select(Offer, StockSnapshot)
        .outerjoin(
            StockSnapshot,
            (StockSnapshot.offer_id == Offer.id)
            & (StockSnapshot.snapshot_date == date.today()),
        )
        .where(Offer.product_id == product_id)
    ).all()
    offer_items = []
    for offer, snapshot in offers:
        offer_items.append(
            OfferOut(
                competitor_id=offer.competitor_id,
                competitor_name=names.get(offer.competitor_id, str(offer.competitor_id)),
                url=offer.url,
                price=float(snapshot.price) if snapshot and snapshot.price is not None else None,
                old_price=(
                    float(snapshot.old_price)
                    if snapshot and snapshot.old_price is not None
                    else None
                ),
                discount_pct=(
                    float(snapshot.discount_pct)
                    if snapshot and snapshot.discount_pct is not None
                    else None
                ),
                qty=snapshot.qty if snapshot else None,
                qty_text=snapshot.qty_text if snapshot else None,
                availability=snapshot.availability if snapshot else "unknown",
                status_text=snapshot.status_text if snapshot else None,
                warehouse=snapshot.warehouse if snapshot else None,
                delivery_time=snapshot.delivery_time if snapshot else None,
                snapshot_date=(
                    snapshot.snapshot_date.isoformat() if snapshot and snapshot.snapshot_date else None
                ),
            )
        )

    since = date.today() - timedelta(days=SERIES_DAYS)
    daily_rows = db.execute(
        select(ProductDaily)
        .where(ProductDaily.product_id == product_id, ProductDaily.day >= since)
        .order_by(ProductDaily.day.asc())
    ).scalars()
    series = [
        SeriesPoint(
            day=row.day.isoformat(),
            qty_total=row.qty_total,
            offers_total=row.offers_total,
            min_price=float(row.min_price) if row.min_price is not None else None,
            avg_price=float(row.avg_price) if row.avg_price is not None else None,
            max_price=float(row.max_price) if row.max_price is not None else None,
            delta=row.delta,
            change_kind=row.change_kind,
        )
        for row in daily_rows
    ]

    stats = db.get(ProductStats, product_id)
    stats_payload: dict[str, Any] | None = None
    if stats is not None:
        stats_payload = {
            "rating": stats.rating,
            "index_score": float(stats.index_score or 0),
            "index_parts": stats.index_parts,
            "days_observed": stats.days_observed,
            "sale_days": stats.sale_days,
            "frequency_pct": float(stats.frequency_pct or 0),
            "sales_1": stats.sales_1,
            "sales_7": stats.sales_7,
            "sales_14": stats.sales_14,
            "sales_30": stats.sales_30,
            "sales_60": stats.sales_60,
            "sales_90": stats.sales_90,
            "restocks_30": stats.restocks_30,
            "avg_daily_sales": float(stats.avg_daily_sales or 0),
            "competitors_count": stats.competitors_count,
            "in_stock_competitors": stats.in_stock_competitors,
            "min_price": float(stats.min_price) if stats.min_price is not None else None,
            "max_price": float(stats.max_price) if stats.max_price is not None else None,
            "avg_price": float(stats.avg_price) if stats.avg_price is not None else None,
            "median_price": float(stats.median_price) if stats.median_price is not None else None,
            "price_delta": float(stats.price_delta) if stats.price_delta is not None else None,
            "price_changed_at": (
                stats.price_changed_at.isoformat() if stats.price_changed_at else None
            ),
        }

    return ProductDetail(
        product={
            "id": product.id,
            "title": product.title,
            "brand": product.brand,
            "manufacturer": product.manufacturer,
            "oem": product.oem,
            "article": product.article,
            "alt_numbers": product.alt_numbers,
            "applicability": product.applicability,
            "category": product.category,
            "vanished": product.vanished,
            "first_seen_at": product.first_seen_at.isoformat() if product.first_seen_at else None,
        },
        stats=stats_payload,
        offers=offer_items,
        series=series,
        note=DISCLAIMER,
    )


# ---------------------------------------------------------------- отчёты и топ
@router.get("/report/latest")
def report_latest(db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.execute(
        select(DailyReport).order_by(DailyReport.day.desc()).limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Отчётов ещё нет")
    return {"day": row.day.isoformat(), "payload": row.payload}


@router.get("/report/{day}")
def report_by_day(day: date, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.get(DailyReport, day)
    if row is None:
        raise HTTPException(status_code=404, detail="Отчёт за эту дату не найден")
    return {"day": row.day.isoformat(), "payload": row.payload}


@router.get("/top", response_model=list[TopItem])
def top(
    kind: str = Query(default="demand", pattern="^(demand|sales|competitive)$"),
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[TopItem]:
    order = {
        "demand": ProductStats.index_score.desc(),
        "sales": ProductStats.sales_30.desc(),
        "competitive": ProductStats.competitors_count.desc(),
    }[kind]
    rows = db.execute(
        select(Product, ProductStats)
        .join(ProductStats, ProductStats.product_id == Product.id)
        .order_by(order, ProductStats.product_id)
        .limit(limit)
    ).all()
    return [
        TopItem(
            id=p.id,
            title=p.title,
            brand=p.brand,
            oem=p.oem or p.article,
            category=p.category,
            rating=s.rating,
            index_score=float(s.index_score or 0),
            sales_7=s.sales_7,
            sales_30=s.sales_30,
            frequency_pct=float(s.frequency_pct or 0),
            competitors_count=s.competitors_count,
            min_price=float(s.min_price) if s.min_price is not None else None,
            median_price=float(s.median_price) if s.median_price is not None else None,
        )
        for p, s in rows
    ]


# ---------------------------------------------------------------- веса индекса
@router.get("/index-weights", response_model=list[IndexWeightOut])
def get_weights(db: Session = Depends(get_db)) -> list[IndexWeightOut]:
    ensure_index_weights(db)
    rows = db.execute(select(IndexWeight)).scalars()
    return [
        IndexWeightOut(key=w.key, label=w.label, weight=float(w.weight), enabled=w.enabled)
        for w in rows
    ]


@router.put("/index-weights", response_model=list[IndexWeightOut])
def put_weights(payload: list[IndexWeightIn], db: Session = Depends(get_db)) -> list[IndexWeightOut]:
    ensure_index_weights(db)
    known = {w.key: w for w in db.execute(select(IndexWeight)).scalars()}
    for item in payload:
        row = known.get(item.key)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Неизвестный вес: {item.key}")
        row.weight = item.weight
        row.enabled = item.enabled
    db.commit()
    return get_weights(db)


@router.post("/analytics/recompute")
def recompute(db: Session = Depends(get_db)) -> dict[str, Any]:
    from ..services.analytics import recompute_stats
    from ..services.report import build_daily_report

    day = date.today()
    result = recompute_stats(db, day)
    report = build_daily_report(db, day)
    db.commit()
    return {"analytics": result, "report_day": report.get("day")}


# ---------------------------------------------------------------- выгрузка Excel
@router.get("/export")
def export_excel(
    day: date | None = None,
    history_days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> Response:
    """Файл .xlsx с 4 листами: Сводка, Аналитика спроса, Цены конкурентов, Остатки и изменения."""
    from io import BytesIO

    from ..services.excel_export import export_workbook

    target = day or date.today()
    buffer = BytesIO()
    workbook = export_workbook(db, target, history_days)
    workbook.save(buffer)
    filename = f"monitoring_{target.isoformat()}.xlsx"
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------- настройки
@router.get("/settings")
def get_app_settings() -> dict[str, Any]:
    return {
        "app_name": settings.app_name,
        "scheduler_enabled": settings.scheduler_enabled,
        "schedule_hour": settings.schedule_hour,
        "schedule_minute": settings.schedule_minute,
        "timezone": settings.timezone,
        "vanished_grace_days": settings.vanished_grace_days,
        "history_days_required_for_rating": settings.history_days_required_for_rating,
        "max_pages_per_site": settings.max_pages_per_site,
        "http_delay_sec": settings.http_delay_sec,
        "browser_enabled": settings.browser_enabled,
        "retention_months": settings.retention_months,
    }

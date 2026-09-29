from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    CH_DISAPPEARED,
    CH_RESTOCK,
    CH_SALE,
    Competitor,
    DailyReport,
    Offer,
    ParserRun,
    Product,
    ProductStats,
    StockSnapshot,
)


def build_daily_report(db: Session, day: date) -> dict[str, Any]:
    """Собирает сводку за день (п.3, 20 ТЗ) и сохраняет её в daily_reports."""
    snapshots_today = db.execute(
        select(
            StockSnapshot.change_kind,
            func.count(StockSnapshot.id),
            func.coalesce(func.sum(func.abs(func.coalesce(StockSnapshot.delta, 0))), 0),
        )
        .where(StockSnapshot.snapshot_date == day)
        .group_by(StockSnapshot.change_kind)
    ).all()
    by_kind = {kind: (count, total) for kind, count, total in snapshots_today}
    sales_count, sales_units = by_kind.get(CH_SALE, (0, 0))
    restock_count, restock_units = by_kind.get(CH_RESTOCK, (0, 0))
    vanished_count, _ = by_kind.get(CH_DISAPPEARED, (0, 0))

    totals = {
        "products": db.execute(select(func.count(Product.id))).scalar() or 0,
        "offers": db.execute(select(func.count(Offer.id))).scalar() or 0,
        "active_offers": db.execute(select(func.count(Offer.id)).where(Offer.active.is_(True))).scalar() or 0,
        "offers_seen_today": db.execute(select(func.count(Offer.id)).where(Offer.seen_on == day)).scalar() or 0,
        "new_products": db.execute(select(func.count(Product.id)).where(func.date(Product.created_at) == day)).scalar()
        or 0,
        "sales_events": int(sales_count),
        "sales_units": int(sales_units),
        "restock_events": int(restock_count),
        "restock_units": int(restock_units),
        "disappeared": int(vanished_count),
    }

    rating_rows = db.execute(
        select(ProductStats.rating, func.count(ProductStats.product_id)).group_by(ProductStats.rating)
    ).all()
    ratings = dict(rating_rows)

    top_demand = _top_products(db, order_by=ProductStats.index_score.desc(), limit=20)
    top_sales = _top_products(db, order_by=ProductStats.sales_30.desc(), limit=20)
    top_competitive = _top_products(db, order_by=ProductStats.competitors_count.desc(), limit=20)

    competitor_rows = []
    for competitor in db.execute(select(Competitor).order_by(Competitor.sort_order)).scalars():
        offers = (
            db.execute(
                select(func.count(Offer.id)).where(Offer.competitor_id == competitor.id, Offer.seen_on == day)
            ).scalar()
            or 0
        )
        last_run = db.execute(
            select(ParserRun)
            .where(ParserRun.competitor_id == competitor.id)
            .order_by(ParserRun.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        competitor_rows.append(
            {
                "id": competitor.id,
                "name": competitor.name,
                "url": competitor.base_url,
                "enabled": competitor.enabled,
                "offers_today": int(offers),
                "last_status": last_run.status if last_run else None,
                "last_error": last_run.error_message if last_run else None,
                "last_run_at": last_run.started_at.isoformat() if last_run else None,
            }
        )

    payload: dict[str, Any] = {
        "day": day.isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "totals": totals,
        "ratings": ratings,
        "top_demand": top_demand,
        "top_sales_30": top_sales,
        "top_competitive": top_competitive,
        "competitors": competitor_rows,
        "note": "Предполагаемые продажи рассчитаны по снижению остатков и не являются фактическими.",
    }

    existing = db.get(DailyReport, day)
    if existing is None:
        db.add(DailyReport(day=day, payload=payload))
    else:
        existing.payload = payload
    db.flush()
    return payload


def _top_products(db: Session, *, order_by, limit: int) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Product, ProductStats)
        .join(ProductStats, ProductStats.product_id == Product.id)
        .order_by(order_by, ProductStats.product_id)
        .limit(limit)
    ).all()
    result = []
    for product, stats in rows:
        result.append(
            {
                "id": product.id,
                "title": product.title,
                "brand": product.brand,
                "oem": product.oem or product.article,
                "category": product.category,
                "rating": stats.rating,
                "index_score": float(stats.index_score or 0),
                "sales_7": stats.sales_7,
                "sales_30": stats.sales_30,
                "frequency_pct": float(stats.frequency_pct or 0),
                "competitors_count": stats.competitors_count,
                "min_price": float(stats.min_price) if stats.min_price is not None else None,
                "median_price": float(stats.median_price) if stats.median_price is not None else None,
            }
        )
    return result

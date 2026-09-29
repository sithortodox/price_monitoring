from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    AV_IN_STOCK,
    DEFAULT_INDEX_WEIGHTS,
    DEMAND_WINDOWS,
    IndexWeight,
    Offer,
    ProductDaily,
    ProductStats,
    StockSnapshot,
)

log = logging.getLogger("services.analytics")


def ensure_index_weights(db: Session) -> list[IndexWeight]:
    """Создаёт настраиваемые веса индекса спроса, если их ещё нет (п.12 ТЗ)."""
    existing = {w.key for w in db.execute(select(IndexWeight)).scalars()}
    for key, label, weight in DEFAULT_INDEX_WEIGHTS:
        if key not in existing:
            db.add(IndexWeight(key=key, label=label, weight=weight, enabled=True))
    db.commit()
    return list(db.execute(select(IndexWeight)).scalars())


def _series(db: Session, since: date) -> dict[int, list[ProductDaily]]:
    rows = (
        db.execute(
            select(ProductDaily)
            .where(ProductDaily.day >= since)
            .order_by(ProductDaily.day.asc())
            .execution_options(yield_per=5000)
        )
        .scalars()
        .all()
    )
    series: dict[int, list[ProductDaily]] = defaultdict(list)
    for row in rows:
        series[row.product_id].append(row)
    return series


def _window_sales(rows: list[ProductDaily], days: int, day: date) -> int:
    start = day - timedelta(days=days - 1)
    total = 0
    for row in rows:
        if row.day < start or row.day > day:
            continue
        if row.delta is not None and row.delta > 0:
            total += row.delta
    return total


def recompute_stats(db: Session, day: date) -> dict[str, Any]:
    """Пересчитывает окна спроса, рейтинг и индекс закупки по всем товарам (п.8–12 ТЗ)."""
    ensure_index_weights(db)
    weights = {w.key: float(w.weight) for w in db.execute(select(IndexWeight)).scalars() if w.enabled}

    series = _series(db, day - timedelta(days=100))
    competitors = dict(
        db.execute(
            select(Offer.product_id, func.count(func.distinct(Offer.competitor_id))).group_by(Offer.product_id)
        ).all()
    )
    in_stock = dict(
        db.execute(
            select(StockSnapshot.product_id, func.count(func.distinct(StockSnapshot.competitor_id)))
            .where(StockSnapshot.snapshot_date == day, StockSnapshot.availability == AV_IN_STOCK)
            .group_by(StockSnapshot.product_id)
        ).all()
    )
    prices_today: dict[int, list[float]] = defaultdict(list)
    price_rows = db.execute(
        select(StockSnapshot.product_id, StockSnapshot.price).where(
            StockSnapshot.snapshot_date == day, StockSnapshot.price.is_not(None)
        )
    ).all()
    for product_id, price in price_rows:
        prices_today[product_id].append(float(price))

    price_change_info: dict[int, tuple[date, float]] = {}
    for product_id, rows in series.items():
        with_price = [r for r in rows if r.day <= day and r.min_price is not None]
        if len(with_price) >= 2:
            last, prev = with_price[-1], with_price[-2]
            if float(last.min_price or 0) != float(prev.min_price or 0):
                price_change_info[product_id] = (
                    last.day,
                    round(float(last.min_price or 0) - float(prev.min_price or 0), 2),
                )

    computed = 0
    for product_id, rows in series.items():
        if not rows:
            continue
        window_values = {w: _window_sales(rows, w, day) for w in DEMAND_WINDOWS}
        observed = [r for r in rows if r.day <= day]
        days_observed = len(observed)
        sale_days = sum(1 for r in observed if r.delta is not None and r.delta > 0)
        frequency = round(sale_days / days_observed * 100, 1) if days_observed else 0.0
        restocks_30 = sum(
            1 for r in observed if r.delta is not None and r.delta < 0 and r.day >= day - timedelta(days=30)
        )

        latest = observed[-1]
        prices = prices_today.get(product_id, [])
        avg_price = latest.avg_price
        min_price = latest.min_price
        max_price = latest.max_price
        median_price = round(median(prices), 2) if prices else avg_price

        price_delta = None
        price_changed_at = None
        change = price_change_info.get(product_id)
        if change:
            price_changed_at, price_delta = change

        competitors_count = int(competitors.get(product_id, 0))
        in_stock_count = int(in_stock.get(product_id, 0))
        avg_daily = round(window_values[30] / max(1, min(30, days_observed)), 3)

        rating = _rating(days_observed, frequency, window_values[30], window_values[7])
        parts = _index_parts(
            sales_30=window_values[30],
            sales_7=window_values[7],
            frequency=frequency,
            competitors=competitors_count,
            availability=in_stock_count,
            price_changed=price_changed_at is not None and (day - price_changed_at).days <= 7,
            observation=days_observed,
        )
        score = _index_score(parts, weights)

        stats = db.get(ProductStats, product_id)
        if stats is None:
            stats = ProductStats(product_id=product_id)
            db.add(stats)
        stats.computed_at = datetime.now()
        stats.days_observed = days_observed
        stats.sale_days = sale_days
        stats.frequency_pct = frequency
        stats.sales_1 = window_values[1]
        stats.sales_7 = window_values[7]
        stats.sales_14 = window_values[14]
        stats.sales_30 = window_values[30]
        stats.sales_60 = window_values[60]
        stats.sales_90 = window_values[90]
        stats.restocks_30 = restocks_30
        stats.avg_daily_sales = avg_daily
        stats.competitors_count = competitors_count
        stats.in_stock_competitors = in_stock_count
        stats.min_price = min_price
        stats.max_price = max_price
        stats.avg_price = avg_price
        stats.median_price = median_price
        stats.price_delta = price_delta
        stats.price_changed_at = price_changed_at
        stats.rating = rating
        stats.index_score = score
        stats.index_parts = parts
        computed += 1

    db.commit()
    return {"products": computed, "weights": len(weights)}


def _rating(days_observed: int, frequency: float, sales_30: int, sales_7: int) -> str:
    """Рейтинг востребованности: A/B/C/D/NEW (п.9 ТЗ)."""
    if days_observed < settings.history_days_required_for_rating:
        return "NEW"
    if frequency >= 50 and sales_30 >= 5:
        return "A"
    if frequency >= 25 and sales_30 >= 2:
        return "B"
    if sales_30 >= 1 or sales_7 >= 1 or frequency >= 10:
        return "C"
    return "D"


def _index_parts(
    *,
    sales_30: int,
    sales_7: int,
    frequency: float,
    competitors: int,
    availability: int,
    price_changed: bool,
    observation: int,
) -> dict[str, float]:
    """Нормализованные факторы индекса 0..1 (п.12 ТЗ)."""
    return {
        "sales_30": round(min(1.0, sales_30 / 30), 3),
        "sales_7": round(min(1.0, sales_7 / 10), 3),
        "frequency": round(min(1.0, frequency / 100), 3),
        "competitors": round(min(1.0, competitors / 10), 3),
        "availability": round(min(1.0, availability / max(1, competitors)), 3),
        "price_change": 1.0 if price_changed else 0.5,
        "observation": round(min(1.0, observation / 30), 3),
    }


def _index_score(parts: dict[str, float], weights: dict[str, float]) -> float:
    num = 0.0
    den = 0.0
    for key, weight in weights.items():
        if key not in parts:
            continue
        num += weight * parts[key]
        den += weight
    if den == 0:
        return 0.0
    return round(num / den * 100, 1)

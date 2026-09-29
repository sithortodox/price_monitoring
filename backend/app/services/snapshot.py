from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    AV_DISAPPEARED,
    AV_OUT_OF_STOCK,
    CH_DISAPPEARED,
    CH_FIRST,
    CH_NONE,
    CH_RESTOCK,
    CH_SALE,
    CH_UNKNOWN,
    Offer,
    Product,
    ProductDaily,
    StockSnapshot,
    clip,
)

log = logging.getLogger("services.snapshot")

TodayValues = dict[int, dict[str, Any]]


def write_snapshots(
    db: Session, day: date, today: TodayValues, scope_competitor_ids: list[int] | None = None
) -> dict[str, int]:
    """Сохраняет ежедневный снимок по всем позициям (п.5, 6, 16, 25 ТЗ).

    История не перезаписывается: строка на (offer, date) добавляется один раз,
    повторный запуск в тот же день обновляет только сегодняшнюю строку.
    `today` — offer_id -> актуальные значения из парсера.
    `scope_competitor_ids` — по каким сайтам считать исчезновение (важно при
    внеплановом запуске одного сайта: остальные не должны «исчезнуть»);
    None — считать по всем сайтам, [] — никого не считать исчезнувшим.
    """
    stats = {"written": 0, "updated": 0, "sales": 0, "restocks": 0, "disappeared": 0}
    previous_by_offer = _previous_snapshots(db, day)
    today_by_offer = {
        s.offer_id: s
        for s in db.execute(
            select(StockSnapshot).where(StockSnapshot.snapshot_date == day).execution_options(yield_per=5000)
        ).scalars()
    }

    changed_products: set[int] = set()
    for offer_id, values in today.items():
        offer = db.get(Offer, offer_id)
        if offer is None:
            continue
        previous = previous_by_offer.get(offer_id)
        delta, kind = compute_delta(previous, values)
        snapshot = today_by_offer.get(offer_id)
        if snapshot is None:
            snapshot = StockSnapshot(
                offer_id=offer_id,
                product_id=offer.product_id,
                competitor_id=offer.competitor_id,
                snapshot_date=day,
            )
            db.add(snapshot)
            today_by_offer[offer_id] = snapshot
            stats["written"] += 1
        else:
            stats["updated"] += 1

        apply_values(snapshot, values, delta, kind)
        if kind in (CH_SALE, CH_RESTOCK, "price_changed"):
            changed_products.add(offer.product_id)
        if kind == CH_SALE:
            stats["sales"] += 1
        elif kind == CH_RESTOCK:
            stats["restocks"] += 1

    # Позиции, не увиденные сегодня: помечаем исчезновением, НЕ считаем продажей (п.16)
    today_ids = list(today.keys()) or [0]
    grace_start = day - timedelta(days=settings.vanished_grace_days)
    candidate_query = select(Offer.id, Offer.product_id, Offer.competitor_id).where(
        Offer.last_seen_at >= datetime.combine(grace_start, datetime.min.time()),
        Offer.id.not_in(today_ids),
    )
    if scope_competitor_ids is not None:
        candidate_query = candidate_query.where(Offer.competitor_id.in_(scope_competitor_ids))

    for offer_id, product_id, competitor_id in db.execute(candidate_query).all():
        previous = previous_by_offer.get(offer_id)
        if previous is None or previous.availability == AV_DISAPPEARED:
            continue
        if (day - previous.snapshot_date).days > settings.vanished_grace_days:
            continue
        if offer_id in today_by_offer:
            continue
        db.add(
            StockSnapshot(
                offer_id=offer_id,
                product_id=product_id,
                competitor_id=competitor_id,
                snapshot_date=day,
                price=None,
                old_price=None,
                qty=None,
                qty_text="Товар исчез из каталога",
                availability=AV_DISAPPEARED,
                status_text="Товар исчез из каталога",
                delta=None,
                change_kind=CH_DISAPPEARED,
            )
        )
        stats["disappeared"] += 1

    db.flush()

    if changed_products:
        now = datetime.now()
        for product_id in changed_products:
            product = db.get(Product, product_id)
            if product is not None:
                product.last_changed_at = now
        db.flush()

    rebuild_product_daily(db, day)
    return stats


def _previous_snapshots(db: Session, day: date) -> dict[int, StockSnapshot]:
    """Последний снимок до указанной даты по каждой позиции (одним запросом)."""
    rn = (
        func.row_number()
        .over(partition_by=StockSnapshot.offer_id, order_by=StockSnapshot.snapshot_date.desc())
        .label("rn")
    )
    sub = select(StockSnapshot.id, rn).where(StockSnapshot.snapshot_date < day).subquery()
    ids = select(sub.c.id).where(sub.c.rn == 1)
    rows = db.execute(
        select(StockSnapshot).where(StockSnapshot.id.in_(ids)).execution_options(yield_per=5000)
    ).scalars()
    return {snapshot.offer_id: snapshot for snapshot in rows}


def apply_values(snapshot: StockSnapshot, values: dict[str, Any], delta: int | None, kind: str) -> None:
    snapshot.price = values.get("price")
    snapshot.old_price = values.get("old_price")
    snapshot.qty = values.get("qty")
    snapshot.qty_text = clip(values.get("qty_text"), 200)
    snapshot.availability = values.get("availability") or "unknown"
    snapshot.status_text = clip(values.get("status_text"), 200)
    snapshot.warehouse = clip(values.get("warehouse"), 200)
    snapshot.delivery_time = clip(values.get("delivery_time"), 120)
    snapshot.delta = delta
    snapshot.change_kind = kind


def compute_delta(previous: StockSnapshot | None, values: dict[str, Any]) -> tuple[int | None, str]:
    """Изменение остатка = вчера − сегодня (п.7, 15 ТЗ).

    Рост остатка — «вероятное пополнение склада», а не отрицательные продажи.
    """
    if previous is None:
        return None, CH_FIRST
    if previous.availability == AV_DISAPPEARED:
        return None, CH_FIRST
    qty = values.get("qty")
    if qty is None or previous.qty is None:
        return None, CH_UNKNOWN
    diff = int(previous.qty) - int(qty)
    if diff > 0:
        return diff, CH_SALE
    if diff < 0:
        return diff, CH_RESTOCK
    return 0, CH_NONE


def rebuild_product_daily(db: Session, day: date) -> None:
    """Агрегирует снимки дня по товару: суммарный остаток и цены (база расчёта спроса)."""
    rows = db.execute(
        select(StockSnapshot).where(StockSnapshot.snapshot_date == day).execution_options(yield_per=2000)
    ).scalars()

    grouped: dict[int, list[StockSnapshot]] = defaultdict(list)
    for snapshot in rows:
        grouped[snapshot.product_id].append(snapshot)

    for product_id, snapshots in grouped.items():
        quantities = [int(s.qty) for s in snapshots if s.qty is not None and s.availability != AV_DISAPPEARED]
        prices = [float(s.price) for s in snapshots if s.price is not None]
        qty_total = sum(quantities) if quantities else (0 if snapshots else None)

        record = db.execute(
            select(ProductDaily).where(ProductDaily.product_id == product_id, ProductDaily.day == day)
        ).scalar_one_or_none()
        if record is None:
            record = ProductDaily(product_id=product_id, day=day)
            db.add(record)

        record.qty_total = qty_total
        record.offers_with_qty = len(quantities)
        record.offers_total = len(snapshots)
        record.min_price = min(prices) if prices else None
        record.max_price = max(prices) if prices else None
        record.avg_price = round(sum(prices) / len(prices), 2) if prices else None

        previous = db.execute(
            select(ProductDaily)
            .where(ProductDaily.product_id == product_id, ProductDaily.day < day)
            .order_by(ProductDaily.day.desc())
            .limit(1)
        ).scalar_one_or_none()

        if previous is None:
            record.delta, record.change_kind = None, CH_FIRST
        elif previous.qty_total is None or qty_total is None:
            record.delta, record.change_kind = None, CH_UNKNOWN
        else:
            diff = int(previous.qty_total) - int(qty_total)
            record.delta = diff
            if diff > 0:
                record.change_kind = CH_SALE
            elif diff < 0:
                record.change_kind = CH_RESTOCK
            else:
                record.change_kind = CH_NONE
    db.flush()


def mark_vanished_products(db: Session, day: date) -> None:
    """Товары, исчезнувшие у всех конкурентов, помечаем флагом (п.16 ТЗ)."""
    active = db.execute(
        select(ProductDaily.product_id)
        .where(ProductDaily.day == day, ProductDaily.qty_total.is_not(None))
        .execution_options(yield_per=2000)
    ).scalars()
    active_set = set(active)
    for product in db.execute(select(Product)).scalars().all():
        product.vanished = product.id not in active_set
    db.flush()


def changes_summary(db: Session, day: date) -> dict[str, int]:
    """Сводка изменений дня для главной страницы и отчёта (п.19, 20 ТЗ)."""
    row = db.execute(
        select(
            func.count(func.distinct(StockSnapshot.competitor_id)),
            func.count(StockSnapshot.id),
            func.count(StockSnapshot.id).filter(StockSnapshot.change_kind == CH_SALE),
            func.count(StockSnapshot.id).filter(StockSnapshot.change_kind == CH_RESTOCK),
            func.count(StockSnapshot.id).filter(StockSnapshot.change_kind == CH_FIRST),
            func.count(StockSnapshot.id).filter(StockSnapshot.availability == AV_OUT_OF_STOCK),
            func.count(StockSnapshot.id).filter(
                StockSnapshot.price.is_not(None), StockSnapshot.change_kind != CH_FIRST
            ),
        ).where(StockSnapshot.snapshot_date == day)
    ).one()

    competitors, snapshots, sales, restocks, first_seen, out_of_stock, price_changes = row
    return {
        "competitors": int(competitors or 0),
        "snapshots": int(snapshots or 0),
        "stock_drops": int(sales or 0),
        "stock_growths": int(restocks or 0),
        "new_items": int(first_seen or 0),
        "out_of_stock": int(out_of_stock or 0),
        "price_changes": int(price_changes or 0),
    }

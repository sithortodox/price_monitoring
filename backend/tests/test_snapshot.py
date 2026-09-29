from __future__ import annotations

from datetime import date, datetime, timedelta

from app.models import (
    AV_DISAPPEARED,
    AV_IN_STOCK,
    CH_DISAPPEARED,
    CH_FIRST,
    CH_RESTOCK,
    CH_SALE,
    ProductDaily,
    StockSnapshot,
)
from app.services.snapshot import write_snapshots
from tests.conftest import values

DAY = date(2026, 3, 10)


def _snapshot(db, offer_id, day):
    return db.query(StockSnapshot).filter_by(offer_id=offer_id, snapshot_date=day).one()


def test_first_sale_restock_cycle(db, offer):
    write_snapshots(db, DAY, {offer.id: values(price=1000, qty=10, availability=AV_IN_STOCK)})
    first = _snapshot(db, offer.id, DAY)
    assert first.change_kind == CH_FIRST
    assert first.delta is None
    assert first.qty == 10

    day2 = DAY + timedelta(days=1)
    write_snapshots(db, day2, {offer.id: values(price=980, qty=8, availability=AV_IN_STOCK)})
    sale = _snapshot(db, offer.id, day2)
    assert sale.change_kind == CH_SALE
    assert sale.delta == 2  # вчера 10 - сегодня 8

    day3 = day2 + timedelta(days=1)
    write_snapshots(db, day3, {offer.id: values(price=990, qty=12, availability=AV_IN_STOCK)})
    restock = _snapshot(db, offer.id, day3)
    assert restock.change_kind == CH_RESTOCK
    assert restock.delta == -4  # 8 - 12

    daily = db.query(ProductDaily).filter_by(product_id=offer.product_id, day=day3).one()
    assert daily.qty_total == 12
    assert daily.delta == -4
    assert daily.min_price == 990


def test_vanished_is_not_a_sale(db, offer):
    write_snapshots(db, DAY, {offer.id: values(qty=5, availability=AV_IN_STOCK)})
    offer.last_seen_at = datetime(2026, 3, 11)
    db.commit()

    day2 = DAY + timedelta(days=1)
    stats = write_snapshots(db, day2, {})
    assert stats["disappeared"] == 1
    assert stats["sales"] == 0

    row = _snapshot(db, offer.id, day2)
    assert row.availability == AV_DISAPPEARED
    assert row.change_kind == CH_DISAPPEARED
    assert row.delta is None  # исчезновение не считается продажей


def test_vanished_grace_expiry(db, offer):
    write_snapshots(db, DAY, {offer.id: values(qty=5, availability=AV_IN_STOCK)})
    offer.last_seen_at = datetime(2026, 3, 10)  # давно не появлялся
    db.commit()

    far_day = DAY + timedelta(days=10)  # больше vanished_grace_days (3)
    stats = write_snapshots(db, far_day, {})
    assert stats["disappeared"] == 0
    assert db.query(StockSnapshot).filter_by(offer_id=offer.id, snapshot_date=far_day).count() == 0


def test_scope_limits_disappearance(db, offer, competitor):
    write_snapshots(db, DAY, {offer.id: values(qty=5, availability=AV_IN_STOCK)})
    offer.last_seen_at = datetime(2026, 3, 11)
    db.commit()

    day2 = DAY + timedelta(days=1)
    stats = write_snapshots(db, day2, {}, scope_competitor_ids=[999])
    assert stats["disappeared"] == 0


def test_same_day_rerun_updates_not_duplicates(db, offer):
    write_snapshots(db, DAY, {offer.id: values(qty=10, availability=AV_IN_STOCK)})
    write_snapshots(db, DAY, {offer.id: values(qty=9, availability=AV_IN_STOCK)})
    rows = db.query(StockSnapshot).filter_by(offer_id=offer.id, snapshot_date=DAY).all()
    assert len(rows) == 1
    assert rows[0].qty == 9


def test_long_text_values_are_clipped(db, offer):
    write_snapshots(
        db,
        DAY,
        {
            offer.id: values(
                qty_text="Остаток: " + "х" * 300,
                status_text="Нет в наличии " + "у" * 300,
                warehouse="Склад " + "с" * 300,
                delivery_time="3 дня " + "д" * 200,
            )
        },
    )
    snapshot = _snapshot(db, offer.id, DAY)
    assert len(snapshot.qty_text) <= 200
    assert len(snapshot.status_text) <= 200
    assert len(snapshot.warehouse) <= 200
    assert len(snapshot.delivery_time) <= 120

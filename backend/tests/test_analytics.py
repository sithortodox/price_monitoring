from __future__ import annotations

from datetime import date, timedelta

from app.models import CH_SALE, Product, ProductDaily, ProductStats
from app.services.analytics import recompute_stats

DAY = date(2026, 4, 15)


def _seed_daily(db, product_id: int, days: int = 14, sale_days: int = 6) -> None:
    """Создаёт историю: qty падает на `sale_days` дат в пределах `days`."""
    qty = 100
    sale_positions = {2 * i for i in range(sale_days) if 2 * i < days}
    for offset in range(days):
        day = DAY - timedelta(days=days - 1 - offset)
        before = qty
        if offset in sale_positions:
            qty -= 3
        db.add(
            ProductDaily(
                product_id=product_id,
                day=day,
                qty_total=qty,
                offers_with_qty=1,
                offers_total=1,
                min_price=1000,
                avg_price=1000,
                max_price=1000,
                delta=(before - qty) if (offset in sale_positions or offset > 0) else None,
                change_kind=CH_SALE if offset in sale_positions else "none",
            )
        )
    db.commit()


def test_recompute_windows_and_rating(db):
    product = Product(match_key="AAA1111", title="Деталь A", oem="AAA1111")
    db.add(product)
    db.commit()
    _seed_daily(db, product.id, days=14, sale_days=7)

    result = recompute_stats(db, DAY)
    db.commit()

    assert result["products"] == 1
    stats = db.get(ProductStats, product.id)
    assert stats is not None
    assert stats.days_observed == 14
    assert stats.sales_30 == 21  # 7 просадок по 3 шт.
    assert stats.sales_7 > 0
    assert float(stats.frequency_pct) == 50.0
    assert stats.rating == "A"  # частота >= 50% и продаж >= 5
    assert 0 <= float(stats.index_score) <= 100
    assert float(stats.index_score) > 0
    assert set(stats.index_parts) == {
        "sales_30",
        "sales_7",
        "frequency",
        "competitors",
        "availability",
        "price_change",
        "observation",
    }


def test_new_rating_for_short_history(db):
    product = Product(match_key="BBB2222", title="Деталь B", oem="BBB2222")
    db.add(product)
    db.commit()
    _seed_daily(db, product.id, days=3, sale_days=1)

    recompute_stats(db, DAY)
    db.commit()
    stats = db.get(ProductStats, product.id)
    assert stats is not None
    assert stats.rating == "NEW"
    assert stats.days_observed == 3


def test_no_sales_gives_low_rating(db):
    product = Product(match_key="CCC3333", title="Деталь C", oem="CCC3333")
    db.add(product)
    db.commit()
    qty = 10
    for offset in range(30):
        db.add(
            ProductDaily(
                product_id=product.id,
                day=DAY - timedelta(days=29 - offset),
                qty_total=qty,
                offers_with_qty=1,
                offers_total=1,
                min_price=None,
                delta=0,
                change_kind="none",
            )
        )
    db.commit()

    recompute_stats(db, DAY)
    db.commit()
    stats = db.get(ProductStats, product.id)
    assert stats is not None
    assert stats.sales_30 == 0
    assert stats.frequency_pct == 0
    assert stats.rating == "D"
    assert float(stats.index_score) >= 0

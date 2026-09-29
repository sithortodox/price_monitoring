from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="site-monitoring-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_TMP}/test.db"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["BROWSER_ENABLED"] = "false"
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["HTTP_DELAY_SEC"] = "0"

from app.db import engine  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture
def db():
    from app.db import SessionFactory

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def competitor(db):
    from app.models import Competitor

    row = Competitor(
        name="Тестовый сайт",
        domain="test.example",
        base_url="https://test.example/catalog/",
        parser_key="aac86",
        enabled=True,
        config={"urls": ["https://test.example/catalog/"]},
        sort_order=1,
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def offer(db, competitor):
    from app.models import Offer, Product

    product = Product(match_key="TEST-1", title="Тестовая деталь", oem="TEST-1")
    db.add(product)
    db.flush()
    row = Offer(product_id=product.id, competitor_id=competitor.id, url="https://test.example/p/1")
    db.add(row)
    db.commit()
    return row


def values(**kwargs) -> dict:
    base = {
        "price": None,
        "old_price": None,
        "qty": None,
        "qty_text": None,
        "availability": "unknown",
        "status_text": None,
        "warehouse": None,
        "delivery_time": None,
    }
    base.update(kwargs)
    return base

from __future__ import annotations

import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Product, ProductStats


@pytest.fixture
def client(db):
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_parsers_registry_exposes_11_sites(client):
    body = client.get("/api/parsers").json()
    assert len(body) == 11
    keys = {item["key"] for item in body}
    assert {"aac86", "autoopt", "autopiter", "truckdrive", "shparts"} <= keys


def test_competitors_seeded(client):
    body = client.get("/api/competitors").json()
    assert len(body) == 11
    assert all(item["enabled"] for item in body)


def test_competitor_toggle(client):
    competitor = client.get("/api/competitors").json()[0]
    response = client.patch(
        f"/api/competitors/{competitor['id']}", json={"enabled": False}
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_competitors_include_last_run(client, db):
    from app.models import RUN_SUCCESS, ParserRun

    competitor_id = client.get("/api/competitors").json()[0]["id"]
    db.add(ParserRun(competitor_id=competitor_id, status=RUN_SUCCESS, items_found=42))
    db.commit()

    body = client.get("/api/competitors").json()
    last_run = body[0]["last_run"]
    assert last_run is not None
    assert last_run["status"] == "success"
    assert last_run["items_found"] == 42
    assert last_run["started_at"] is None or "T" in last_run["started_at"]


def test_products_list_and_detail(client, db):
    product = Product(match_key="DDD4444", title="Деталь D", oem="DDD4444")
    db.add(product)
    db.flush()
    db.add(
        ProductStats(
            product_id=product.id,
            rating="A",
            index_score=77.5,
            sales_7=4,
            sales_30=20,
            frequency_pct=60.0,
            days_observed=30,
            competitors_count=2,
            in_stock_competitors=2,
            min_price=900,
            median_price=950,
            max_price=1100,
        )
    )
    db.commit()

    listing = client.get("/api/products", params={"q": "DDD4444"}).json()
    assert listing["total"] == 1
    assert listing["items"][0]["rating"] == "A"
    assert listing["items"][0]["index_score"] == 77.5

    detail = client.get(f"/api/products/{product.id}").json()
    assert detail["product"]["oem"] == "DDD4444"
    assert detail["stats"]["sales_30"] == 20
    assert detail["offers"] == []
    assert detail["series"] == []


def test_top_and_weights(client, db):
    product = Product(match_key="EEE5555", title="Деталь E", oem="EEE5555")
    db.add(product)
    db.flush()
    db.add(ProductStats(product_id=product.id, rating="B", index_score=50, sales_30=6))
    db.commit()

    top = client.get("/api/top", params={"kind": "sales"}).json()
    assert top and top[0]["id"] == product.id

    weights = client.get("/api/index-weights").json()
    assert len(weights) >= 5
    updated = client.put(
        "/api/index-weights",
        json=[{"key": weights[0]["key"], "weight": 4.5, "enabled": True}],
    ).json()
    assert updated[0]["weight"] == 4.5


def test_export_excel(client, db):
    response = client.get("/api/export", params={"day": date.today().isoformat()})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    from io import BytesIO

    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(response.content))
    assert wb.sheetnames == ["Сводка", "Аналитика спроса", "Цены конкурентов", "Остатки и изменения"]


def test_run_status_and_manual_start(client):
    status = client.get("/api/run/status").json()
    assert status["running"] is False

    started = client.post("/api/run", json={"competitor_ids": [999999]}).json()
    assert started["started"] is True
    # дожидаемся конца фонового запуска — иначе он может дописать данные
    # уже в следующий тест (общая SQLite-база)
    for _ in range(100):
        if not client.get("/api/run/status").json()["running"]:
            break
        time.sleep(0.05)
    assert client.get("/api/run/status").json()["running"] is False


def test_missing_report_returns_404(client):
    assert client.get("/api/report/latest").status_code == 404
    assert client.get("/api/report/2020-01-01").status_code == 404


class _FakeProxyResponse:
    status_code = 200


def _fake_httpx_client(captured, raise_error=False):
    import httpx as _httpx

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            if raise_error:
                raise _httpx.ConnectError("connection refused", request=_httpx.Request("GET", url))
            captured["url"] = url
            return _FakeProxyResponse()

    return FakeClient


def test_proxy_check_uses_site_proxy_and_masks_password(client, competitor, db, monkeypatch):
    import app.api.routes as routes

    competitor.config = {"proxy_url": "http://user:secret@10.0.0.1:3128"}
    db.commit()
    captured: dict[str, object] = {}
    monkeypatch.setattr(routes.httpx, "Client", _fake_httpx_client(captured))

    body = client.post(f"/api/competitors/{competitor.id}/proxy-check").json()

    assert body["ok"] is True
    assert body["source"] == "site"
    assert body["status"] == 200
    assert captured["proxy"] == "http://user:secret@10.0.0.1:3128"
    assert captured["url"] == competitor.base_url
    assert "secret" not in body["proxy"]
    assert "***" in body["proxy"]


def test_proxy_check_reports_connection_error(client, competitor, db, monkeypatch):
    import app.api.routes as routes

    competitor.config = {"proxy_url": "http://10.0.0.1:3128"}
    db.commit()
    monkeypatch.setattr(routes.httpx, "Client", _fake_httpx_client({}, raise_error=True))

    body = client.post(f"/api/competitors/{competitor.id}/proxy-check").json()

    assert body["ok"] is False
    assert body["error"] and "ConnectError" in body["error"]


def test_proxy_check_without_proxy_uses_direct_connection(client, competitor, monkeypatch):
    import app.api.routes as routes

    captured: dict[str, object] = {}
    monkeypatch.setattr(routes.httpx, "Client", _fake_httpx_client(captured))

    body = client.post(f"/api/competitors/{competitor.id}/proxy-check").json()

    assert captured.get("proxy") is None
    assert body["source"] == "none"
    assert body["proxy"] is None
    assert body["ok"] is True


def test_proxy_check_not_found(client):
    assert client.post("/api/competitors/999999/proxy-check").status_code == 404

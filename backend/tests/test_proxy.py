from __future__ import annotations

from types import SimpleNamespace

from app.parsers.fetcher import Fetcher, _playwright_proxy, normalize_proxy


def test_normalize_proxy():
    assert normalize_proxy(None) is None
    assert normalize_proxy("   ") is None
    assert normalize_proxy("1.2.3.4:8080") == "http://1.2.3.4:8080"
    assert normalize_proxy("socks5://user:pass@host:1080") == "socks5://user:pass@host:1080"
    assert normalize_proxy("http://1.2.3.4:8080") == "http://1.2.3.4:8080"


def test_playwright_proxy_splits_credentials():
    proxy = _playwright_proxy("http://user:p%40ss@1.2.3.4:8080")

    assert proxy == {"server": "http://1.2.3.4:8080", "username": "user", "password": "p@ss"}


def test_playwright_proxy_rejects_garbage():
    import pytest

    with pytest.raises(ValueError):
        _playwright_proxy("не--url")


def test_fetcher_normalizes_proxy():
    fetcher = Fetcher(delay=0, proxy="1.2.3.4:8080")
    try:
        assert fetcher.proxy == "http://1.2.3.4:8080"
    finally:
        fetcher.close()


def test_runner_passes_competitor_proxy_to_fetcher(db, competitor, monkeypatch):
    from app.services import runner

    captured: dict[str, object] = {}

    class FakeFetcher:
        def __init__(self, delay=None, timeout=None, proxy=None):
            captured["proxy"] = proxy
            self.stats = SimpleNamespace(pages=0, errors=0, error_messages=[])

        def get(self, url):
            return ""

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(runner, "Fetcher", FakeFetcher)
    competitor.config = {"proxy_url": "10.0.0.1:3128"}
    db.commit()

    run, _values = runner.run_competitor(db, competitor, trigger="manual")

    assert captured["proxy"] == "http://10.0.0.1:3128"  # схема добавлена автоматически
    assert captured.get("closed") is True
    assert run.trigger == "manual"


def test_runner_without_proxy_passes_none(db, competitor, monkeypatch):
    from app.services import runner

    captured: dict[str, object] = {}

    class FakeFetcher:
        def __init__(self, delay=None, timeout=None, proxy=None):
            captured["proxy"] = proxy
            self.stats = SimpleNamespace(pages=0, errors=0, error_messages=[])

        def get(self, url):
            return ""

        def close(self):
            pass

    monkeypatch.setattr(runner, "Fetcher", FakeFetcher)
    competitor.config = {}
    db.commit()

    runner.run_competitor(db, competitor, trigger="manual")

    assert captured["proxy"] is None

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field

import httpx

from ..config import settings

log = logging.getLogger("parser.fetch")


@dataclass
class FetchResult:
    url: str
    status: int
    html: str
    elapsed_ms: int
    error: str | None = None


@dataclass
class FetchStats:
    pages: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)


class Fetcher:
    """HTTP-клиент с таймаутами, повторами и вежливой паузой между запросами."""

    def __init__(self, delay: float | None = None, timeout: float | None = None, proxy: str | None = None) -> None:
        self.delay = delay if delay is not None else settings.http_delay_sec
        self.timeout = timeout if timeout is not None else settings.http_timeout
        self.proxy = normalize_proxy(proxy) or normalize_proxy(settings.proxy_url)
        self.stats = FetchStats()
        self._last_request_at: dict[str, float] = {}
        self._client = httpx.Client(
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            },
            timeout=self.timeout,
            follow_redirects=True,
            verify=True,
            proxy=self.proxy,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _throttle(self, domain: str) -> None:
        last = self._last_request_at.get(domain)
        if last is None:
            return
        elapsed = time.monotonic() - last
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed + random.uniform(0.05, 0.35))

    def get(self, url: str, headers: dict[str, str] | None = None) -> FetchResult:
        domain = httpx.URL(url).host or ""
        started = time.monotonic()
        last_error: str | None = None

        for attempt in range(settings.http_retries + 1):
            self._throttle(domain)
            try:
                response = self._client.get(url, headers=headers)
                self._last_request_at[domain] = time.monotonic()
                self.stats.pages += 1
                elapsed_ms = int((time.monotonic() - started) * 1000)
                if response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}"
                    continue
                if response.status_code >= 400:
                    self.stats.errors += 1
                    self.stats.error_messages.append(f"{url}: HTTP {response.status_code}")
                    return FetchResult(url, response.status_code, "", elapsed_ms, f"HTTP {response.status_code}")
                return FetchResult(url, response.status_code, response.text, elapsed_ms)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self._last_request_at[domain] = time.monotonic()
                time.sleep(0.6 * (attempt + 1))

        self.stats.errors += 1
        self.stats.error_messages.append(f"{url}: {last_error}")
        return FetchResult(url, 0, "", int((time.monotonic() - started) * 1000), last_error)


def normalize_proxy(url: str | None) -> str | None:
    """Пусто → None; «host:port» без схемы → http://host:port."""
    if not url or not str(url).strip():
        return None
    value = str(url).strip()
    if "://" not in value:
        value = "http://" + value
    return value


def _playwright_proxy(url: str) -> dict[str, str]:
    """URL прокси → параметры playwright: логин/пароль отдельными полями."""
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(f"некорректный URL прокси: {url!r}")
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server += f":{parsed.port}"
    proxy: dict[str, str] = {"server": server}
    if parsed.username:
        proxy["username"] = unquote(parsed.username)
    if parsed.password:
        proxy["password"] = unquote(parsed.password)
    return proxy


class BrowserFetcher:
    """Рендеринг страниц через Chromium — для сайтов, где контент приходит по JS."""

    def __init__(self, delay: float | None = None, proxy: str | None = None) -> None:
        from playwright.sync_api import sync_playwright

        self.delay = settings.http_delay_sec if delay is None else delay
        self.proxy = normalize_proxy(proxy) or normalize_proxy(settings.proxy_url)
        self._last_request_at: dict[str, float] = {}
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=settings.browser_headless,
            executable_path=settings.browser_executable_path,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = self._browser.new_context(
            user_agent=settings.user_agent,
            locale="ru-RU",
            viewport={"width": 1440, "height": 2000},
            proxy=_playwright_proxy(self.proxy) if self.proxy else None,
        )
        self.stats = FetchStats()

    def close(self) -> None:
        try:
            self._context.close()
            self._browser.close()
        finally:
            self._pw.stop()

    def __enter__(self) -> BrowserFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_html(
        self,
        url: str,
        wait_selector: str | None = None,
        wait_ms: int = 1500,
        wait_selector_timeout: int = 8000,
    ) -> str:
        page = self._context.new_page()
        try:
            if not self._goto(page, url):
                return ""
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=wait_selector_timeout)
                except Exception:
                    # селектор мог не появиться (например, у групповой страницы нет карточек) —
                    # это не ошибка загрузки, просто ждём фиксированное время
                    log.debug("wait_for_selector timeout for %s (%s)", url, wait_selector)
            page.wait_for_timeout(wait_ms)
            html = page.content()
            self.stats.pages += 1
            return html
        except Exception as exc:
            self.stats.errors += 1
            self.stats.error_messages.append(f"{url}: {type(exc).__name__}: {exc}")
            log.warning("browser fetch failed for %s: %s", url, exc)
            return ""
        finally:
            page.close()

    def evaluate(self, url: str, expression: str, wait_ms: int = 2000) -> object | None:
        """Выполнить JS на странице и вернуть результат (например, window.__INITIAL_STATE__)."""
        page = self._context.new_page()
        try:
            if not self._goto(page, url):
                return None
            page.wait_for_timeout(wait_ms)
            return page.evaluate(expression)
        except Exception as exc:
            self.stats.errors += 1
            self.stats.error_messages.append(f"{url}: {type(exc).__name__}: {exc}")
            return None
        finally:
            page.close()

    # --- Служебное ---
    def _goto(self, page: object, url: str) -> bool:
        """Переход на страницу с паузой между запросами и повторами при обрыве связи."""
        domain = httpx.URL(url).host or ""
        last = self._last_request_at.get(domain)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed + random.uniform(0.05, 0.35))

        last_error: str | None = None
        for attempt in range(settings.http_retries + 1):
            try:
                page.goto(url, timeout=int(settings.http_timeout * 1000), wait_until="domcontentloaded")  # type: ignore[attr-defined]
                self._last_request_at[domain] = time.monotonic()
                return True
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self._last_request_at[domain] = time.monotonic()
                log.warning("browser goto failed for %s (attempt %d): %s", url, attempt + 1, exc)
                time.sleep(3.0 * (attempt + 1))  # обрыв соединения чаще всего = сервер просит паузу

        self.stats.errors += 1
        self.stats.error_messages.append(f"{url}: {last_error}")
        return False

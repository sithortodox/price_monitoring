from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import AV_UNKNOWN, Competitor
from .fetcher import BrowserFetcher, Fetcher

log = logging.getLogger("parser.base")


@dataclass
class RawOffer:
    """Сырая позиция, как её отдал сайт. Дальше нормализуется и склеивается."""

    url: str
    title: str
    seller_article: str | None = None
    oem: str | None = None
    alt_numbers: list[str] = field(default_factory=list)
    brand: str | None = None
    manufacturer: str | None = None
    applicability: str | None = None
    category: str | None = None
    price: float | None = None
    old_price: float | None = None
    qty: int | None = None
    qty_text: str | None = None
    availability: str = AV_UNKNOWN
    status_text: str | None = None
    warehouse: str | None = None
    delivery_time: str | None = None
    external_id: str | None = None


@dataclass
class ParseResult:
    offers: list[RawOffer] = field(default_factory=list)
    pages: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BaseSiteParser(ABC):
    """Базовый класс адаптера сайта.

    Реализует обход страниц каталога, извлечение карточек и (опционально) детальные
    страницы для количества товара.
    """

    key: str = ""
    site_name: str = ""
    spec_version: str = "1"
    # URL каталогов по умолчанию; в конкуренте можно переопределить через config["urls"]
    default_urls: ClassVar[list[str]] = []
    # Нужен ли рендер через браузер
    use_browser: bool = False
    # Ожидание при браузерном рендере: селектор появления контента и запасное время, мс
    browser_wait_selector: str | None = None
    browser_wait_selector_timeout: int = 5000
    browser_wait_ms: int = 1500
    # Получать ли количество товара со страницы товара
    detail_enabled_by_default: bool = False
    # Пауза между запросами к одному сайту (None — берётся из настроек)
    delay_sec: float | None = None
    # Сообщение, если не найдено ни одной позиции (и считать ли это предупреждением)
    empty_result_message: str = ""
    empty_is_warning: bool = False

    def __init__(self, fetcher: Fetcher | None = None, browser: BrowserFetcher | None = None):
        self.fetcher = fetcher
        self.browser = browser

    # --- Публичный вход ---
    def parse(self, competitor: Competitor, max_pages: int | None = None) -> ParseResult:
        result = ParseResult()
        urls = self.expand_start_urls(self.list_urls(competitor))
        if not urls:
            result.errors.append("Не заданы URL каталога")
            return result

        seen_urls: set[str] = set()
        pages = 0
        empty_streak = 0
        for start_url in urls:
            page_url: str | None = start_url
            while page_url and (max_pages is None or pages < max_pages):
                if page_url in seen_urls:
                    break
                seen_urls.add(page_url)
                html = self._get(page_url)
                pages += 1
                result.pages += 1
                if not html:
                    if pages <= 1:
                        result.errors.append(f"Не удалось загрузить {page_url}")
                    else:
                        # страница глубокой пагинации обычно просто не существует
                        result.warnings.append(f"Страница {page_url} не загрузилась — обход каталога завершён")
                    empty_streak += 1
                    break
                empty_streak = 0
                try:
                    page_offers, next_url = self.parse_list_page(html, page_url)
                except Exception as exc:
                    result.errors.append(f"{page_url}: {type(exc).__name__}: {exc}")
                    log.exception("parse_list_page failed for %s", page_url)
                    break
                if not page_offers:
                    if pages == 1:
                        result.warnings.append(f"На странице {page_url} не найдено ни одной позиции")
                    break
                for offer in page_offers:
                    if offer.url not in seen_urls:
                        seen_urls.add(offer.url)
                        result.offers.append(offer)
                page_url = next_url
            # несколько пустых ответов подряд — сайт недоступен или блокирует нас:
            # нет смысла продолжать обход оставшихся URL
            if empty_streak >= 3:
                result.errors.append("Сайт не отвечает (сеть/блокировка) — обход прерван")
                break

        if self.needs_details(competitor) and self.fetcher is not None:
            self._enrich_details(result, competitor)

        if not result.offers:
            message = (
                "Парсер не нашёл ни одной позиции — вероятно, изменилась структура сайта"
                if not self.empty_result_message
                else self.empty_result_message
            )
            if self.empty_is_warning:
                result.warnings.append(message)
            else:
                result.errors.append(message)
        return result

    # --- Переопределяемые методы ---
    @abstractmethod
    def parse_list_page(self, html: str, page_url: str) -> tuple[list[RawOffer], str | None]:
        """Возвращает (позиции, ссылка на следующую страницу или None)."""

    def detail_urls(self, offers: list[RawOffer]) -> list[RawOffer]:
        return [o for o in offers if o.qty is None]

    def parse_detail_page(self, html: str, offer: RawOffer) -> RawOffer:
        """Общая реализация: достаём остаток/наличие со страницы товара."""
        from .helpers import extract_qty_from_detail

        if offer.qty is not None:
            return offer
        qty, qty_text, availability, warehouse = extract_qty_from_detail(html)
        if availability != AV_UNKNOWN:
            offer.qty = qty
            offer.qty_text = qty_text or offer.qty_text
            offer.availability = availability
            if warehouse:
                offer.warehouse = warehouse
        return offer

    def list_urls(self, competitor: Competitor) -> list[str]:
        configured = competitor.config.get("urls") if competitor.config else None
        if configured:
            return [str(u) for u in configured]
        return list(self.default_urls)

    def expand_start_urls(self, urls: list[str]) -> list[str]:
        """Хук для парсеров, которым нужно дополнить стартовый список (например, из sitemap)."""
        return urls

    def needs_details(self, competitor: Competitor) -> bool:
        return competitor.detail_enabled or self.detail_enabled_by_default

    # --- Служебное ---
    def _get(self, url: str) -> str:
        if self.use_browser:
            if self.browser is None:
                raise RuntimeError(f"Парсер {self.key} требует браузер, но он не инициализирован")
            return self.browser.get_html(
                url,
                wait_selector=self.browser_wait_selector,
                wait_selector_timeout=self.browser_wait_selector_timeout,
                wait_ms=self.browser_wait_ms,
            )
        if self.fetcher is None:
            raise RuntimeError(f"Парсер {self.key} не имеет HTTP-клиента")
        result = self.fetcher.get(url)
        if result.error:
            log.warning("fetch error %s: %s", url, result.error)
        return result.html

    def _enrich_details(self, result: ParseResult, competitor: Competitor) -> None:
        candidates = self.detail_urls(result.offers)
        limit = int(competitor.config.get("detail_limit", 200) or 200) if competitor.config else 200
        for offer in candidates[:limit]:
            html = self._get(offer.url)
            if not html:
                continue
            try:
                self.parse_detail_page(html, offer)
            except Exception as exc:
                result.errors.append(f"{offer.url}: {type(exc).__name__}: {exc}")

    @staticmethod
    def soup(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    @staticmethod
    def absolute(base: str, href: str | None) -> str | None:
        if not href:
            return None
        return urljoin(base, href)

    @staticmethod
    def text(node: Any) -> str | None:
        if node is None:
            return None
        value = node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node)
        return value or None

from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from ...models import AV_IN_STOCK, AV_UNKNOWN
from ..base import BaseSiteParser, RawOffer
from ..helpers import clean
from ..normalize import old_price_and_discount, parse_price, parse_quantity

# Страницы-группы каталога отдают дерево, а карточки — только на листовых группах,
# поэтому стартовый URL разворачивается в список листовых групп.
_GROUP_RE = re.compile(r"search_cataloggroup=([^&#]+)", re.I)
_SHACL_GROUP_RE = re.compile(r"shacman|shaanxi|x3000|x6000", re.I)
_CARD_SELECTOR = ".catalog-products-plate__product-item"
_MAX_DISCOVER_PAGES = 40


class TruckdriveParser(BaseSiteParser):
    """truckdrive.ru — список товаров рендерится через JS, поэтому используем браузер.

    Страницы-группы (например, вся ветка SHACMAN) не содержат карточек: товары
    отдаются только на листовых подгруппах. Поэтому перед обходом собираем такие
    подгруппы, а на каждой листовой странице ставим 500 позиций на страницу.
    """

    key = "truckdrive"
    site_name = "TruckDrive (truckdrive.ru)"
    default_urls: ClassVar[list[str]] = [
        "https://truckdrive.ru/catalog/?search_cataloggroup=katalog-zapchasti-dlya-gruzovikov-shacman"
    ]
    use_browser = True
    # сайт чувствителен к частым запросам — делаем паузу между загрузками
    delay_sec = 3.0
    browser_wait_selector: str | None = _CARD_SELECTOR
    browser_wait_selector_timeout = 5000
    browser_wait_ms = 1000

    def __init__(self, fetcher=None, browser=None) -> None:
        super().__init__(fetcher=fetcher, browser=browser)
        self._page_cache: dict[str, str] = {}

    def expand_start_urls(self, urls: list[str]) -> list[str]:
        """Находит листовые группы каталога, в которых есть карточки товаров."""
        if self.browser is None:
            return urls

        leaves: list[str] = []
        seen: set[str] = set()
        queue = [u for u in urls if u]
        scanned = 0
        fail_streak = 0
        while queue and scanned < _MAX_DISCOVER_PAGES:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            scanned += 1
            # сразу запрашиваем 500 позиций на страницу: тогда разобранный HTML
            # переиспользуется на этапе обхода без повторной загрузки
            fetch_url = self._with_perpage(url)
            html = self._get(fetch_url)
            if not html:
                fail_streak += 1
                if fail_streak >= 3:  # сайт недоступен или блокирует — не продолжаем
                    break
                continue
            fail_streak = 0
            soup = self.soup(html)
            if soup.select(_CARD_SELECTOR):
                leaves.append(fetch_url)
                continue
            for link in soup.select("a[href*='search_cataloggroup=']"):
                href = self.absolute(fetch_url, link.get("href"))
                if not href or href in seen:
                    continue
                match = _GROUP_RE.search(href)
                if match and _SHACL_GROUP_RE.search(match.group(1)):
                    queue.append(href)
        return list(dict.fromkeys(leaves)) if leaves else urls

    def parse_list_page(self, html: str, page_url: str) -> tuple[list[RawOffer], str | None]:
        soup = self.soup(html)
        offers: list[RawOffer] = []
        for node in soup.select(_CARD_SELECTOR):
            # первым в карточке идёт ссылка-картинка без текста, поэтому имя берём отдельно
            link = node.select_one("a.catalog-products-plate__product-name[href]") or node.select_one(
                "a[href*='/details/catalog/product/']"
            )
            if not link:
                continue
            url = self.absolute(page_url, link.get("href"))
            img = node.select_one("img[alt]")
            title = clean(self.text(link)) or clean(link.get("title")) or clean(img.get("alt") if img else None)
            if not url or not title:
                continue

            brand = clean(self.text(node.select_one(".catalog-products-plate__product-brand")))
            article = clean(self.text(node.select_one(".catalog-products-plate__product-art")))
            price = parse_price(self.text(node.select_one(".catalog-products-plate__product-min-price")))

            stock_node = node.select_one("[class*=stock], [class*=count], [class*=qty]")
            stock_text = clean(self.text(stock_node))
            qty, qty_text, availability = parse_quantity(stock_text) if stock_text else (None, None, AV_UNKNOWN)
            if availability == AV_UNKNOWN:
                availability = AV_IN_STOCK if price is not None else AV_UNKNOWN

            old_price, _ = old_price_and_discount(price, None)
            offers.append(
                RawOffer(
                    url=url,
                    title=title,
                    seller_article=article,
                    brand=brand,
                    price=price,
                    old_price=old_price,
                    qty=qty,
                    qty_text=qty_text or stock_text,
                    availability=availability,
                    status_text=stock_text,
                )
            )
        return offers, self._next_url(page_url, len(offers))

    # --- Служебное ---
    def _get(self, url: str) -> str:
        cached = self._page_cache.get(url)
        if cached is not None:
            return cached
        html = super()._get(url)
        if html:
            self._page_cache[url] = html
        return html

    @staticmethod
    def _with_perpage(url: str, perpage: int = 500) -> str:
        """Ставит 500 позиций на страницу — чтобы обойти каталог за меньше загрузок."""
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        query["catalog_perpage"] = [str(perpage)]
        query.pop("catalog_page", None)
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    @staticmethod
    def _next_url(page_url: str, items: int) -> str | None:
        """Следующая страница: сайт использует параметр catalog_page."""
        if items <= 0:
            return None
        parsed = urlparse(page_url)
        query = parse_qs(parsed.query)
        try:
            perpage = int(query.get("catalog_perpage", ["24"])[0])
        except ValueError:
            perpage = 24
        if items < perpage:
            return None
        try:
            current = int(query.get("catalog_page", ["1"])[0])
        except ValueError:
            current = 1
        new_query = dict(query)
        new_query["catalog_page"] = [str(current + 1)]
        return urlunparse(parsed._replace(query=urlencode(new_query, doseq=True)))

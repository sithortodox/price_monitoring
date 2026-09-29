from __future__ import annotations

import json
import re
from typing import ClassVar

from ..base import BaseSiteParser, RawOffer
from ..helpers import clean, find_next_page
from ..normalize import (
    AV_UNKNOWN,
    availability_from_schema,
    old_price_and_discount,
    parse_price,
)

_STOCKS_RE = re.compile(r'"stocks"\s*:\s*(\[.*?\])', re.S)
_PRICE_RE = re.compile(r'"price"\s*:\s*(\d{2,})')


class RelinesParser(BaseSiteParser):
    """relines.ru — список через schema.org, количество со страницы товара (JSON «stocks»)."""

    key = "relines"
    site_name = "Рилайнс (relines.ru)"
    default_urls: ClassVar[list[str]] = ["https://relines.ru/catalog/shacman"]
    detail_enabled_by_default = True

    def parse_list_page(self, html: str, page_url: str) -> tuple[list[RawOffer], str | None]:
        soup = self.soup(html)
        offers: list[RawOffer] = []
        for node in soup.select(".catalog-product-list-item"):
            link = node.select_one("a[href]")
            if not link:
                continue
            url = self.absolute(page_url, link.get("href"))
            title = clean(self.text(node.select_one('[itemprop="name"]')) or node.get("data-content"))
            if not url or not title:
                continue

            sku_node = node.select_one('[itemprop="sku"]')
            article = clean(self.text(sku_node)) if sku_node else None
            if not article:
                sku_span = node.select_one(".sku-code")
                article = clean(self.text(sku_span)) if sku_span else None

            price_meta = node.select_one('meta[itemprop="price"]')
            price = parse_price(
                price_meta.get("content")
                if price_meta
                else self.text(node.select_one(".catalog-product-list-item__price"))
            )

            avail_link = node.select_one('link[itemprop="availability"]')
            availability = availability_from_schema(avail_link.get("href") if avail_link else None)
            if availability is None:
                availability = AV_UNKNOWN
            qty: int | None = None
            qty_text: str | None = None

            old_price, _ = old_price_and_discount(price, None)
            offers.append(
                RawOffer(
                    url=url,
                    title=title,
                    seller_article=article,
                    price=price,
                    old_price=old_price,
                    qty=qty,
                    qty_text=qty_text,
                    availability=availability,
                )
            )
        return offers, find_next_page(html, page_url)

    def parse_detail_page(self, html: str, offer: RawOffer) -> RawOffer:
        match = _STOCKS_RE.search(html)
        if not match:
            return offer
        try:
            stocks = json.loads(match.group(1))
        except (ValueError, TypeError):
            return offer
        if not isinstance(stocks, list) or not stocks:
            return offer
        counts = [int(s.get("count") or 0) for s in stocks if isinstance(s, dict)]
        total = sum(counts)
        names = [str(s.get("name") or "") for s in stocks if isinstance(s, dict)]
        availability = str(stocks[0].get("availability") or "")
        if availability == "onDemand" and total == 0:
            offer.availability = "on_order"
            offer.qty = None
            offer.qty_text = "Под заказ"
        elif total > 0:
            offer.qty = total
            offer.availability = "in_stock"
            offer.qty_text = f"На складах: {total}"
        if names:
            offer.warehouse = ", ".join(n for n in names if n)[:200]

        price_match = _PRICE_RE.search(html)
        if price_match and not offer.price:
            offer.price = parse_price(int(price_match.group(1)) / 100)
        return offer

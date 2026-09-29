from __future__ import annotations

import re
from typing import ClassVar

from ..base import BaseSiteParser, RawOffer
from ..helpers import clean, find_next_page
from ..normalize import old_price_and_discount, parse_price, parse_quantity

_ART_RE = re.compile(r"Арт\.?\s*[:：]\s*([^\s|]+)", re.I)
_QTY_RE = re.compile(r"В наличии\s*[:：]\s*(\d+)", re.I)


class TransekParser(BaseSiteParser):
    """trans-ek.ru — Bitrix: .catalog-block-view__item, «В наличии : 10», «Арт.: LEO100183A»."""

    key = "transek"
    site_name = "Транс-ЭК (trans-ek.ru)"
    default_urls: ClassVar[list[str]] = ["https://trans-ek.ru/catalog/shacman/"]

    def parse_list_page(self, html: str, page_url: str) -> tuple[list[RawOffer], str | None]:
        soup = self.soup(html)
        offers: list[RawOffer] = []
        for node in soup.select(".catalog-block-view__item"):
            title_node = node.select_one(".item-title a[href], .item-title")
            if not title_node:
                continue
            link = title_node if title_node.name == "a" else title_node.select_one("a[href]")
            href = link.get("href") if link else node.select_one("a.dark_link[href]")
            url = self.absolute(page_url, href)
            title = clean(self.text(title_node))
            if not url or not title:
                continue

            stock_node = node.select_one(".item-stock .value, .item-stock")
            stock_text = clean(self.text(stock_node))
            qty, qty_text, availability = parse_quantity(stock_text)

            full_text = clean(node.get_text(" ", strip=True), 600) or ""
            art_match = _ART_RE.search(full_text)
            article = art_match.group(1) if art_match else None
            if qty is None:
                qty_match = _QTY_RE.search(stock_text or "")
                if qty_match:
                    qty = int(qty_match.group(1))

            price = parse_price(self.text(node.select_one(".price_value")))
            old_price = parse_price(self.text(node.select_one(".price_old, .old-price")))
            old_price, _ = old_price_and_discount(price, old_price)

            offers.append(
                RawOffer(
                    url=url,
                    title=title,
                    seller_article=article,
                    price=price,
                    old_price=old_price,
                    qty=qty,
                    qty_text=qty_text or stock_text,
                    availability=availability,
                    status_text=stock_text,
                )
            )
        return offers, find_next_page(html, page_url)

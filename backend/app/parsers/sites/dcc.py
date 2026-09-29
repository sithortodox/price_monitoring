from __future__ import annotations

from typing import ClassVar

from ..base import BaseSiteParser, RawOffer
from ..helpers import clean, find_next_page
from ..normalize import AV_IN_STOCK, old_price_and_discount, parse_price


class DccParser(BaseSiteParser):
    """1dcc.ru (ДСС) — каталог OpenCart: .catalog_item, цена вида «4,095 р.»."""

    key = "dcc"
    site_name = "ДСС (1dcc.ru)"
    default_urls: ClassVar[list[str]] = ["https://1dcc.ru/shaanxi/"]

    def parse_list_page(self, html: str, page_url: str) -> tuple[list[RawOffer], str | None]:
        soup = self.soup(html)
        offers: list[RawOffer] = []
        for node in soup.select(".catalog_item"):
            name_node = node.select_one(".catalog_name a[href]")
            if not name_node:
                continue
            url = self.absolute(page_url, name_node.get("href"))
            title = clean(self.text(name_node))
            if not url or not title:
                continue

            model_node = node.select_one(".catalog_model .text-muted, .catalog_model")
            article = clean(self.text(model_node))

            price = parse_price(self.text(node.select_one(".catalog_price")))
            if price is None:
                data_node = node.select_one("[data-price]")
                price = parse_price(data_node.get("data-price") if data_node else None)

            has_cart = node.select_one("a.to_cart, a[href*='checkout/cart']")
            availability = AV_IN_STOCK if has_cart else "unknown"
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
                    status_text="В корзину" if has_cart else None,
                )
            )
        return offers, find_next_page(html, page_url)

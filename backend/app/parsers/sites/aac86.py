from __future__ import annotations

from typing import ClassVar

from ..base import BaseSiteParser, RawOffer
from ..helpers import clean, find_next_page
from ..normalize import (
    old_price_and_discount,
    parse_price,
    parse_quantity,
)


class Aac86Parser(BaseSiteParser):
    """aac86.ru — каталог с data-атрибутами (data-price, data-stock) и schema.org."""

    key = "aac86"
    site_name = "АвтоАгрегатЦентр (aac86.ru)"
    default_urls: ClassVar[list[str]] = ["https://aac86.ru/catalog/shakman/"]

    def parse_list_page(self, html: str, page_url: str) -> tuple[list[RawOffer], str | None]:
        soup = self.soup(html)
        offers: list[RawOffer] = []
        for node in soup.select(".catalog-item"):
            url = None
            link = node.select_one("a[href]")
            meta_url = node.select_one('meta[itemprop="url"]')
            if meta_url and meta_url.get("content"):
                url = meta_url["content"]
            elif link:
                url = self.absolute(page_url, link.get("href"))
            title = node.get("data-name") or self.text(node.select_one('[itemprop="name"]'))
            if not url or not title:
                continue

            price = parse_price(node.get("data-price"))
            old_price = parse_price(node.get("data-origprice")) or None
            if old_price and price and old_price <= price:
                old_price = None
            qty, qty_text, availability = parse_quantity(node.get("data-stock"))
            if availability == "in_stock" and qty == 0:
                qty, availability = 0, "out_of_stock"

            stock_node = node.select_one(".blk_stock")
            status = clean(self.text(stock_node)) if stock_node else None

            brand_node = node.select_one('meta[itemprop="brand"] meta[itemprop="name"], [itemprop=brand] meta')
            brand = None
            if brand_node:
                brand = brand_node.get("content")

            article = clean(self.text(node.select_one(".art_value")))
            old_price, _discount = old_price_and_discount(price, old_price)

            offers.append(
                RawOffer(
                    url=url,
                    title=clean(title) or "",
                    seller_article=article,
                    brand=brand,
                    price=price,
                    old_price=old_price,
                    qty=qty,
                    qty_text=qty_text,
                    availability=availability,
                    status_text=status,
                )
            )
        return offers, find_next_page(html, page_url)

from __future__ import annotations

from typing import ClassVar

from ..base import BaseSiteParser, RawOffer
from ..helpers import clean, find_next_page
from ..normalize import old_price_and_discount, parse_price, parse_quantity


class StugsParser(BaseSiteParser):
    """stugs.ru — InSales: .products__item, код товара, новая/старая цена."""

    key = "stugs"
    site_name = "Stugs (stugs.ru)"
    default_urls: ClassVar[list[str]] = ["https://stugs.ru/category/shaanxi-shacman/"]

    def parse_list_page(self, html: str, page_url: str) -> tuple[list[RawOffer], str | None]:
        soup = self.soup(html)
        offers: list[RawOffer] = []
        for node in soup.select(".products__item"):
            link = node.select_one("a[href]:not([class])") or node.select_one("a[href]")
            name_node = node.select_one('[itemprop="name"]')
            if not link or not name_node:
                continue
            url = self.absolute(page_url, link.get("href"))
            title = clean(self.text(name_node))
            if not url or not title:
                continue

            code_node = node.select_one(".products__code-v")
            article = clean(self.text(code_node))

            price = parse_price(self.text(node.select_one(".products__price-new")))
            old_price = parse_price(self.text(node.select_one(".products__price-old")))
            if price is None:
                price = old_price
                old_price = None

            stock_node = node.select_one(".products__available")
            stock_text = clean(self.text(stock_node))
            qty, qty_text, availability = parse_quantity(stock_text)
            if availability == "in_stock" and qty is None and stock_text:
                qty_text = stock_text

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

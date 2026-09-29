from __future__ import annotations

from typing import ClassVar

from ..base import BaseSiteParser, RawOffer
from ..helpers import clean, find_next_page
from ..normalize import old_price_and_discount, parse_price, parse_quantity


class GlavmehParser(BaseSiteParser):
    """ГлавМех (xn--80aebk1ai8d.xn--p1ai) — MasterShop: артикул, «Ориг. №», розничная цена."""

    key = "glavmeh"
    site_name = "ГлавМех.рф"
    default_urls: ClassVar[list[str]] = ["https://xn--80aebk1ai8d.xn--p1ai/zapchasti-shaanxi/"]

    def parse_list_page(self, html: str, page_url: str) -> tuple[list[RawOffer], str | None]:
        soup = self.soup(html)
        offers: list[RawOffer] = []
        for node in soup.select(".product-list__item"):
            name_node = node.select_one("a.product-list__name")
            if not name_node:
                continue
            url = self.absolute(page_url, name_node.get("href"))
            title = clean(self.text(name_node))
            if not url or not title:
                continue

            article = clean(self.text(node.select_one(".product-list__code")))
            if article and article.lower().startswith("артикул"):
                article = clean(article.split(":", 1)[1]) if ":" in article else article

            oem = None
            for row in node.select(".product_features-item"):
                label = clean(self.text(row.select_one(".product_features-title")))
                value = clean(self.text(row.select_one(".product_features-value")))
                if not label or not value:
                    continue
                low = label.lower()
                if "ориг" in low or "oem" in low or "оригинал" in low:
                    oem = value
                elif "бренд" in low or "производител" in low:
                    pass

            price = parse_price(self.text(node.select_one(".product-list__price")))
            opt_node = node.select_one(".product-list__prices font")
            old_price = None
            stock_node = node.select_one(".product-list__stock")
            stock_text = clean(self.text(stock_node))
            qty, qty_text, availability = parse_quantity(stock_text)
            status = stock_text
            if price is None and opt_node:
                price = parse_price(clean(self.text(opt_node)))
            old_price, _discount = old_price_and_discount(price, old_price)

            offers.append(
                RawOffer(
                    url=url,
                    title=title,
                    seller_article=article,
                    oem=oem,
                    price=price,
                    old_price=old_price,
                    qty=qty,
                    qty_text=qty_text,
                    availability=availability,
                    status_text=status,
                )
            )
        return offers, find_next_page(html, page_url)

from __future__ import annotations

import re
from typing import ClassVar

from ..base import BaseSiteParser, RawOffer
from ..helpers import clean, find_next_page
from ..normalize import old_price_and_discount, parse_price, parse_quantity

_SITEMAP_RE = re.compile(r"<loc>\s*([^<]+/magazin/folder/\d+[^<]*)\s*</loc>", re.I)


class ShpartsParser(BaseSiteParser):
    """sh-parts.ru — Shop2: карточки с артикулом, брендом и количеством «В наличии 1»."""

    key = "shparts"
    site_name = "Shacman Parts (sh-parts.ru)"
    default_urls: ClassVar[list[str]] = ["https://sh-parts.ru/magazin/folder/24199707"]
    detail_enabled_by_default = False

    def expand_start_urls(self, urls: list[str]) -> list[str]:
        if not self.fetcher or len(urls) > 1:
            return urls
        sitemap = self.fetcher.get("https://sh-parts.ru/sitemap.xml")
        if not sitemap.html:
            return urls
        folders = list(dict.fromkeys(m.strip() for m in _SITEMAP_RE.findall(sitemap.html)))
        limit = 20
        if folders:
            return folders[:limit]
        return urls

    def parse_list_page(self, html: str, page_url: str) -> tuple[list[RawOffer], str | None]:
        soup = self.soup(html)
        offers: list[RawOffer] = []
        for node in soup.select(".shop2-product-item"):
            link = node.select_one(".gr-product-name a[href]")
            if link is None:
                link = node.select_one("a[href*='product/']")
            if link is None:
                continue
            url = self.absolute(page_url, link.get("href"))
            title = clean(self.text(link)) or clean(link.get("title") or link.get("aria-label") or "")
            if not url or not title:
                continue

            article_node = node.select_one(".product-article")
            article = None
            if article_node:
                text = clean(self.text(article_node)) or ""
                article = text.split(":", 1)[1].strip() if ":" in text else text or None

            brand_node = node.select_one(".gr-vendor-block a, .gr-vendor-block")
            brand = clean(self.text(brand_node))

            price = parse_price(self.text(node.select_one(".price-current strong, .price-current")))
            old_price = parse_price(self.text(node.select_one(".price-old, .price-old strong")))

            stock_node = node.select_one(".gr-amount-flag")
            stock_text = clean(self.text(stock_node))
            qty, qty_text, availability = parse_quantity(stock_text)
            if availability == "in_stock" and qty is None and stock_node:
                ins = stock_node.select_one("ins")
                if ins and clean(self.text(ins)):
                    qty, qty_text = int(clean(self.text(ins)) or 0), stock_text
            if "нет" in (stock_text or "").lower():
                availability, qty = "out_of_stock", 0
            if not stock_text:
                # часть карточек без .gr-amount-flag — статус в кнопке корзины
                card_low = clean(self.text(node), 400) or ""
                if "нет в наличии" in card_low.lower():
                    availability, qty, qty_text, stock_text = "out_of_stock", 0, "Нет в наличии", "Нет в наличии"
                elif "под заказ" in card_low.lower():
                    availability, qty_text, stock_text = "on_order", "Под заказ", "Под заказ"

            old_price, _ = old_price_and_discount(price, old_price)
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
        return offers, find_next_page(html, page_url)

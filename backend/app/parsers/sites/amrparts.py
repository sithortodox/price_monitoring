from __future__ import annotations

import re
from typing import ClassVar

from ..base import BaseSiteParser, RawOffer
from ..helpers import clean, find_next_page
from ..normalize import old_price_and_discount, parse_price

_ART_RE = re.compile(r"Артикул\s*:\s*([^\s<]+)", re.I)
_QTY_RE = re.compile(r"В наличии[^:：]{0,60}[:：]\s*(\d+)\s*шт", re.I)


class AmrpartsParser(BaseSiteParser):
    """amrparts.ru (Автомагистраль) — Bitrix-каталог; количество и цена со страницы товара."""

    key = "amrparts"
    site_name = "Автомагистраль (amrparts.ru)"
    default_urls: ClassVar[list[str]] = [
        "https://amrparts.ru/catalog/shacman/",
        "https://amrparts.ru/catalog/faw/",
        "https://amrparts.ru/catalog/sinotruk/",
    ]
    detail_enabled_by_default = True

    def parse_list_page(self, html: str, page_url: str) -> tuple[list[RawOffer], str | None]:
        soup = self.soup(html)
        offers: list[RawOffer] = []
        for node in soup.select(".catalog-product"):
            link = node.select_one("a[href]")
            if not link:
                continue
            url = self.absolute(page_url, link.get("href"))
            title = clean(self.text(node.select_one(".showcase-catalog-title")))
            if not url or not title:
                continue

            id_node = node.select_one(".catalog-id")
            article = None
            if id_node:
                text = clean(self.text(id_node)) or ""
                match = _ART_RE.search(text)
                article = match.group(1) if match else text.split(":", 1)[-1].strip() or None

            price = parse_price(self.text(node.select_one(".catalog-price__actual-digit")))
            status = clean(self.text(node.select_one(".catalog-price__item")))
            if price is None and status:
                status_text = status  # «Узнать цену»
            else:
                status_text = None

            old_price, _ = old_price_and_discount(price, None)
            offers.append(
                RawOffer(
                    url=url,
                    title=title,
                    seller_article=article,
                    price=price,
                    old_price=old_price,
                    availability="unknown",
                    status_text=status_text,
                )
            )
        return offers, find_next_page(html, page_url)

    def parse_detail_page(self, html: str, offer: RawOffer) -> RawOffer:
        soup = self.soup(html)
        text = clean(soup.get_text(" ", strip=True), 6000) or ""
        qty_match = _QTY_RE.search(text)
        if qty_match:
            offer.qty = int(qty_match.group(1))
            offer.availability = "in_stock"
            offer.qty_text = f"{offer.qty} шт"
            offer.status_text = "В наличии"
        elif "нет в наличии" in text.lower():
            offer.qty = 0
            offer.availability = "out_of_stock"
            offer.qty_text = "Нет в наличии"
        else:
            return super().parse_detail_page(html, offer)

        if offer.price is None:
            price_node = soup.select_one("[itemprop=price], .catalog-price__actual-digit, .price")
            src = price_node.get("content") if price_node and price_node.name == "meta" else self.text(price_node)
            price = parse_price(src)
            if price:
                offer.price = price
        brand_node = soup.select_one("[itemprop=brand] meta[itemprop=name], .brand a, .brands-item-label")
        if brand_node and not offer.brand:
            offer.brand = brand_node.get("content") or clean(self.text(brand_node))
        return offer

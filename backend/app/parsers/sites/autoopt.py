from __future__ import annotations

import re
from typing import ClassVar

from ..base import BaseSiteParser, RawOffer
from ..helpers import clean, find_next_page
from ..normalize import old_price_and_discount, parse_price, parse_quantity

_ART_RE = re.compile(r"Артикул\s*:\s*(\S+)")
_CODE_RE = re.compile(r"Код для заказа\s*:\s*(\S+)")
_DELIVERY_RE = re.compile(r"(\d+\s*(?:дн|час|дней)[\.\s]*)", re.I)


class AutooptParser(BaseSiteParser):
    """autoopt.ru — цены и остатки подгружаются по JS, поэтому страница рендерится в браузере."""

    key = "autoopt"
    site_name = "АвтоАльянс (autoopt.ru)"
    default_urls: ClassVar[list[str]] = [
        "https://www.autoopt.ru/catalog/zapchasti_dlya_shacman_shaanxi_gruzovye"
        "?CatalogGroupForm%5Bgroups%5D%5B%5D=1598&filter=right"
    ]
    use_browser = True
    browser_wait_selector: str | None = ".n-catalog-item__price-count"
    browser_wait_selector_timeout = 5000
    browser_wait_ms = 1500

    def parse_list_page(self, html: str, page_url: str) -> tuple[list[RawOffer], str | None]:
        soup = self.soup(html)
        offers: list[RawOffer] = []
        for node in soup.select(".n-catalog-item__product, .n-catalog-item.grid-item"):
            link = node.select_one("a[href^='/catalog/']")
            if not link:
                continue
            url = self.absolute(page_url, link.get("href"))
            title = clean(self.text(link))
            if not url or not title or title.startswith("Перейти к странице"):
                continue

            price_block = node.select_one(".n-catalog-item__price-count")
            block_text = clean(self.text(price_block), 400) if price_block else ""
            if not block_text:
                continue

            art_match = _ART_RE.search(block_text)
            code_match = _CODE_RE.search(block_text)
            article = art_match.group(1) if art_match else None
            external_id = code_match.group(1) if code_match else None
            if not article:
                article_node = node.select_one(".n-catalog-item__article")
                article = clean(self.text(article_node)) or external_id

            # в контейнере бренда лежит попап с описанием — имя берём из заголовка попапа
            brand_node = node.select_one(".n-catalog-item__brand .popup-brand__title span")
            brand = clean(self.text(brand_node))

            price = parse_price(self.text(node.select_one(".price-item, .n-catalog-item__price")))
            if price is None:
                price_match = re.search(r"(\d[\d\s]*(?:,\d{1,2})?)\s*₽", block_text)
                price = parse_price(price_match.group(1)) if price_match else None

            old_price = parse_price(
                self.text(node.select_one(".price-old, .price-old-price, .n-catalog-item__price-old"))
            )

            # карточка бывает двух видов: «59 шт.» / «113 в наличии» / «Нет в наличии» /
            # «Под заказ». Блок цены содержит и цену, и остаток — разбираем его целиком,
            # а узел .link-color.fake используем только как запасной источник.
            qty_node = node.select_one(".link-color.fake, .n-catalog-item__qty, [class*=quantity]")
            qty, qty_text, availability = parse_quantity(block_text)
            if qty is None and availability == "unknown" and qty_node:
                q2, t2, a2 = parse_quantity(self.text(qty_node))
                if q2 is not None or a2 != "unknown":
                    qty, qty_text, availability = q2, t2, a2

            delivery = None
            delivery_match = _DELIVERY_RE.search(block_text)
            if delivery_match:
                delivery = clean(delivery_match.group(1))

            if qty is None and availability == "unknown" and "под заказ" in block_text.lower():
                availability = "on_order"

            old_price, _ = old_price_and_discount(price, old_price)
            offers.append(
                RawOffer(
                    url=url,
                    title=title,
                    seller_article=article,
                    external_id=external_id,
                    brand=brand,
                    price=price,
                    old_price=old_price,
                    qty=qty,
                    qty_text=qty_text or clean(self.text(qty_node)),
                    availability=availability,
                    delivery_time=delivery,
                    status_text=clean(block_text, 120),
                )
            )
        return offers, find_next_page(html, page_url)

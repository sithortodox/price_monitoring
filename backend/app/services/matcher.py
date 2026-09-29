from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Product, ProductAlias, clip
from ..parsers.base import RawOffer
from ..parsers.normalize import extract_numbers, normalize_key

log = logging.getLogger("services.matcher")

_ALIAS_KINDS = ("oem", "article", "alt", "title")


class ProductMatcher:
    """Склеивает одинаковые товары разных конкурентов (п.17 ТЗ).

    Основной идентификатор — OEM / артикул производителя / каталожный номер /
    кросс-номер. Название используется только как дополнительный фактор.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._cache: dict[str, int | None] = {}

    def match(self, offer: RawOffer) -> Product:
        keys = self.candidate_keys(offer)
        product_id: int | None = None

        # 1. точное совпадение по OEM/артикулу/кросс-номерам
        for key, _kind in keys:
            if key in self._cache:
                product_id = self._cache[key]
                break
            found = self.db.execute(
                select(ProductAlias.product_id).where(ProductAlias.alias == key)
            ).scalar_one_or_none()
            if found:
                product_id = found
                break

        # 2. совпадение по нормализованному названию
        if product_id is None:
            title_key = self._title_key(offer.title)
            if title_key:
                found = self.db.execute(
                    select(ProductAlias.product_id).where(ProductAlias.alias == title_key)
                ).scalar_one_or_none()
                product_id = found

        if product_id is None:
            product = self._create(offer, keys)
            product_id = product.id
        else:
            product = self.db.get(Product, product_id)
            if product is None:  # pragma: no cover — гонка удаления
                product = self._create(offer, keys)
                product_id = product.id
            else:
                self._merge_details(product, offer)

        for key, _kind in keys:
            self._cache[key] = product_id
        title_key = self._title_key(offer.title)
        if title_key:
            self._cache.setdefault(title_key, product_id)

        self._store_aliases(product, offer, keys)
        return product

    # --- helpers ---
    @staticmethod
    def candidate_keys(offer: RawOffer) -> list[tuple[str, str]]:
        keys: list[tuple[str, str]] = []
        for value, kind in (
            (offer.oem, "oem"),
            (offer.seller_article, "article"),
        ):
            norm = clip(normalize_key(value), 128) or ""
            if len(norm) >= 4:
                keys.append((norm, kind))
        for value in offer.alt_numbers:
            norm = clip(normalize_key(value), 128) or ""
            if len(norm) >= 6:
                keys.append((norm, "alt"))
        seen: set[str] = set()
        unique: list[tuple[str, str]] = []
        for key, kind in keys:
            if key not in seen:
                seen.add(key)
                unique.append((key, kind))
        return unique

    @staticmethod
    def _title_key(title: str | None) -> str | None:
        if not title:
            return None
        key = clip(normalize_key(title), 128) or ""
        return key if len(key) >= 10 else None

    def _create(self, offer: RawOffer, keys: list[tuple[str, str]]) -> Product:
        match_key = keys[0][0] if keys else (self._title_key(offer.title) or normalize_key(offer.url))
        product = Product(
            match_key=match_key[:128],
            title=clip(offer.title, 500) or "",
            brand=clip(offer.brand, 200),
            manufacturer=clip(offer.manufacturer, 200),
            oem=clip(normalize_key(offer.oem), 128) or None,
            article=clip(normalize_key(offer.seller_article), 128) or None,
            alt_numbers=list(offer.alt_numbers),
            applicability=clip(offer.applicability, 500),
            category=clip(offer.category, 300),
        )
        self.db.add(product)
        self.db.flush()
        return product

    @staticmethod
    def _merge_details(product: Product, offer: RawOffer) -> None:
        if offer.oem and not product.oem:
            product.oem = clip(normalize_key(offer.oem), 128) or None
        if offer.seller_article and not product.article:
            product.article = clip(normalize_key(offer.seller_article), 128) or None
        if offer.brand and not product.brand:
            product.brand = clip(offer.brand, 200)
        if offer.manufacturer and not product.manufacturer:
            product.manufacturer = clip(offer.manufacturer, 200)
        if offer.applicability and not product.applicability:
            product.applicability = clip(offer.applicability, 500)
        if offer.category and not product.category:
            product.category = clip(offer.category, 300)
        if offer.alt_numbers:
            merged = list(dict.fromkeys([*(product.alt_numbers or []), *offer.alt_numbers]))
            product.alt_numbers = merged[:20]

    def _store_aliases(self, product: Product, offer: RawOffer, keys: list[tuple[str, str]]) -> None:
        aliases = list(keys)
        title_key = self._title_key(offer.title)
        if title_key:
            aliases.append((title_key, "title"))
        if not aliases:
            url_key = normalize_key(offer.url)[-64:]
            if url_key:
                aliases.append((url_key, "alt"))
        for key, kind in aliases:
            exists = self.db.execute(select(ProductAlias.id).where(ProductAlias.alias == key)).scalar_one_or_none()
            if exists:
                continue
            self.db.add(ProductAlias(product_id=product.id, alias=key[:128], kind=kind))
        self.db.flush()


def alt_numbers_from_title(title: str) -> list[str]:
    """Достаёт кросс-номера, перечисленные в названии товара."""
    return extract_numbers(title)

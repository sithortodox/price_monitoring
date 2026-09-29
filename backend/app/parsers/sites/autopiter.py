from __future__ import annotations

import json
import re
from typing import ClassVar

from ...models import Competitor
from ..base import BaseSiteParser, ParseResult, RawOffer
from ..helpers import clean
from ..normalize import old_price_and_discount, parse_price

_STATE_RE = re.compile(r"window\['__INITIAL_STATE__'\]\s*=\s*(\{[\s\S]*?\});?\s*</script>")


class AutopiterParser(BaseSiteParser):
    """autopiter.ru — SPA. Номенклатуру отдаёт внутренний API /api/api/catalog/russian/*:

    список моделей -> список групп (GroupId) -> детали группы -> detailscosts по номерам
    (цена и остаток). Если API не отдаёт детали без авторизации, парсер сообщает об этом
    как о предупреждении, а не как об ошибке структуры сайта.
    """

    key = "autopiter"
    site_name = "Автопитер (autopiter.ru)"
    default_urls: ClassVar[list[str]] = ["https://autopiter.ru/russiancatalog/shaanxi"]
    api_base = "https://autopiter.ru/api/api/catalog/russian"
    empty_result_message = "Автопитер не отдаёт номенклатуру анонимно (нужен вход или другой город) — данные не собраны"
    empty_is_warning = True
    # API деталей без авторизации отвечает ошибкой — не молотим его по всем группам
    _api_failure_limit = 5
    _api_failures: int = 0

    def parse(self, competitor: Competitor, max_pages: int | None = None) -> ParseResult:
        result = ParseResult()
        model_urls: list[str] = []
        seen: set[str] = set()
        self._api_failures = 0

        for start_url in self.list_urls(competitor):
            html = self._get(start_url)
            result.pages += 1
            if not html:
                result.errors.append(f"Не удалось загрузить {start_url}")
                continue
            state = self._state(html)
            if not state:
                result.errors.append(f"На {start_url} не найден window.__INITIAL_STATE__")
                continue

            details = (state.get("russianCatalog") or {}).get("details") or {}
            if details.get("groupDetails"):
                model_urls.append(start_url)
                continue

            models = ((state.get("russianCatalog") or {}).get("models") or {}).get("models") or []
            brand = details.get("brandSlug") or (state.get("russianCatalog") or {}).get("models", {}).get(
                "brandSlug", ""
            )
            limit = int(competitor.config.get("model_limit", 15) or 15)
            for model in models[:limit]:
                slug = model.get("engShortName")
                if not slug:
                    continue
                model_urls.append(f"https://autopiter.ru/russiancatalog/{brand}/{slug}")

        seen_offer_urls: set[str] = set()
        for url in model_urls:
            if max_pages is not None and result.pages >= max_pages:
                break
            if url in seen:
                continue
            seen.add(url)
            html = self._get(url)
            result.pages += 1
            if not html:
                result.warnings.append(f"Не удалось загрузить {url}")
                continue
            state = self._state(html)
            if not state:
                continue
            details = (state.get("russianCatalog") or {}).get("details") or {}
            brand_slug = details.get("brandSlug") or ""
            model_slug = details.get("modelSlug") or ""
            groups = details.get("groupDetails") or []
            if not (brand_slug and model_slug and groups):
                continue
            for group in groups[:20]:
                group_id = group.get("id")
                if not group_id:
                    continue
                offers = self._fetch_group(brand_slug, model_slug, int(group_id), group.get("name"), url)
                for offer in offers:
                    if offer.url not in seen_offer_urls:
                        seen_offer_urls.add(offer.url)
                        result.offers.append(offer)
                if not result.offers and self._api_failures >= self._api_failure_limit:
                    result.warnings.append("API деталей autopiter.ru не отвечает анонимно — обход прерван")
                    return result

        if not result.offers:
            if result.errors:
                return result
            result.warnings.append(self.empty_result_message)
        return result

    def parse_list_page(self, html: str, page_url: str) -> tuple[list[RawOffer], str | None]:
        state = self._state(html) or {}
        details = (state.get("russianCatalog") or {}).get("details") or {}
        groups = details.get("groupDetails") or []
        offers: list[RawOffer] = []
        for group in groups:
            if not group.get("id"):
                continue
            offers.extend(
                self._fetch_group(
                    details.get("brandSlug", ""),
                    details.get("modelSlug", ""),
                    int(group["id"]),
                    group.get("name"),
                    page_url,
                )
            )
        return offers, None

    @staticmethod
    def _state(html: str) -> dict | None:
        match = _STATE_RE.search(html)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except (ValueError, TypeError):
            return None

    def _fetch_group(
        self, brand: str, model: str, group_id: int, group_name: str | None, page_url: str
    ) -> list[RawOffer]:
        if not self.fetcher:
            return []
        params = (
            "meta%5BfrontendType%5D=1&meta%5BrenderType%5D=1"
            f"&meta%5BrouteId%5D=RUSSIAN_CATALOG_DETAIL&modelName={model}&GroupId={group_id}"
        )
        result = self.fetcher.get(f"{self.api_base}/details?{params}")
        if not result.html:
            self._api_failures += 1
            return []
        try:
            payload = json.loads(result.html)
        except (ValueError, TypeError):
            return []
        data = payload.get("data") or {}
        items = data.get("details") or []
        category = clean(str(data.get("groupName") or group_name or ""))

        offers: list[RawOffer] = []
        numbers: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            number = clean(str(item.get("number") or "")) or ""
            title = clean(str(item.get("name") or item.get("detailName") or "")) or number
            if not title:
                continue
            offers.append(
                RawOffer(
                    url=page_url,
                    title=title,
                    seller_article=number or None,
                    oem=number or None,
                    brand=clean(str(item.get("brand") or "")) or None,
                    category=category,
                    availability="unknown",
                )
            )
            if number:
                numbers.append(number)

        costs = self._fetch_costs(numbers)
        for offer, cost in zip(offers, costs, strict=False):
            if not cost:
                continue
            offer.price = cost.get("priceMin")
            max_price = cost.get("priceMax")
            offer.old_price = max_price if max_price and max_price != offer.price else None
            qty = cost.get("quantity")
            if qty is not None:
                offer.qty = int(qty)
                offer.availability = "in_stock" if int(qty) > 0 else "out_of_stock"
                offer.qty_text = f"{qty} шт"
            offer.old_price, _ = old_price_and_discount(offer.price, offer.old_price)
        return offers

    def _fetch_costs(self, numbers: list[str]) -> list[dict | None]:
        if not numbers or not self.fetcher:
            return []
        joined = ",".join(numbers[:100])
        params = (
            "meta%5BfrontendType%5D=1&meta%5BrenderType%5D=1"
            f"&meta%5BrouteId%5D=RUSSIAN_CATALOG_DETAIL&numbersString={joined}"
        )
        result = self.fetcher.get(f"{self.api_base}/detailscosts?{params}")
        if not result.html:
            return []
        try:
            payload = json.loads(result.html)
        except (ValueError, TypeError):
            return []
        by_number: dict[str, dict] = {}
        for row in payload.get("data") or []:
            if isinstance(row, dict) and row.get("number"):
                by_number[str(row["number"]).upper()] = {
                    "priceMin": parse_price(row.get("priceMin")),
                    "priceMax": parse_price(row.get("priceMax")),
                    "quantity": row.get("quantity"),
                }
        return [by_number.get(number.upper()) for number in numbers]

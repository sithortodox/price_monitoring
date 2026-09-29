from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    status: str
    app: str
    database: str
    time: str


class ParserInfo(BaseModel):
    key: str
    name: str
    urls: str
    use_browser: str


class RunBrief(BaseModel):
    """Краткая информация о последнем запуске парсера (для списка конкурентов)."""

    id: int
    status: str
    started_at: datetime | None = None
    duration_ms: int = 0
    items_found: int = 0
    errors_count: int = 0
    error_message: str | None = None

    model_config = {"from_attributes": True}


class CompetitorOut(BaseModel):
    id: int
    name: str
    domain: str
    base_url: str
    parser_key: str
    enabled: bool
    detail_enabled: bool
    config: dict[str, Any] = {}
    categories: list[str] = []
    note: str | None = None
    sort_order: int
    last_run: RunBrief | None = None
    offers_total: int = 0
    offers_today: int = 0

    model_config = {"from_attributes": True}


class CompetitorPatch(BaseModel):
    enabled: bool | None = None
    detail_enabled: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = None
    config: dict[str, Any] | None = None


class RunStartIn(BaseModel):
    competitor_ids: list[int] | None = None


class RunOut(BaseModel):
    id: int
    competitor_id: int
    competitor_name: str | None = None
    trigger: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    pages_fetched: int
    items_found: int
    offers_written: int
    errors_count: int
    error_message: str | None = None
    duration_ms: int


class ProductListItem(BaseModel):
    id: int
    title: str
    brand: str | None = None
    oem: str | None = None
    category: str | None = None
    rating: str
    index_score: float
    sales_7: int
    sales_14: int
    sales_30: int
    sales_90: int
    frequency_pct: float
    days_observed: int
    competitors_count: int
    in_stock_competitors: int
    min_price: float | None = None
    median_price: float | None = None
    max_price: float | None = None
    price_delta: float | None = None
    qty_total: int | None = None


class ProductPage(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    items: list[ProductListItem]


class OfferOut(BaseModel):
    competitor_id: int
    competitor_name: str
    url: str
    price: float | None = None
    old_price: float | None = None
    discount_pct: float | None = None
    qty: int | None = None
    qty_text: str | None = None
    availability: str
    status_text: str | None = None
    warehouse: str | None = None
    delivery_time: str | None = None
    snapshot_date: str | None = None


class SeriesPoint(BaseModel):
    day: str
    qty_total: int | None = None
    offers_total: int = 0
    min_price: float | None = None
    avg_price: float | None = None
    max_price: float | None = None
    delta: int | None = None
    change_kind: str


class ProductDetail(BaseModel):
    product: dict[str, Any]
    stats: dict[str, Any] | None = None
    offers: list[OfferOut]
    series: list[SeriesPoint]
    note: str


class TopItem(BaseModel):
    id: int
    title: str
    brand: str | None = None
    oem: str | None = None
    category: str | None = None
    rating: str
    index_score: float
    sales_7: int
    sales_30: int
    frequency_pct: float
    competitors_count: int
    min_price: float | None = None
    median_price: float | None = None


class IndexWeightIn(BaseModel):
    key: str
    weight: float = Field(ge=0, le=10)
    enabled: bool = True


class IndexWeightOut(BaseModel):
    key: str
    label: str
    weight: float
    enabled: bool

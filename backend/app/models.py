from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# --- Статусы наличия (п.16 ТЗ) ---
AV_IN_STOCK = "in_stock"  # в наличии (в т.ч. с количеством)
AV_OUT_OF_STOCK = "out_of_stock"  # нет в наличии -> 0
AV_ON_ORDER = "on_order"  # под заказ -> остаток неизвестен
AV_MANY = "many"  # «Много» -> количество неизвестно
AV_UNKNOWN = "unknown"
AV_DISAPPEARED = "disappeared"  # товар исчез из каталога


def clip(value: str | None, limit: int) -> str | None:
    """Обрезает строку до длины колонки: данные сайтов бывают длиннее схемы."""
    if value is None:
        return None
    return value[:limit]

AVAILABILITY_CHOICES = (
    AV_IN_STOCK,
    AV_OUT_OF_STOCK,
    AV_ON_ORDER,
    AV_MANY,
    AV_UNKNOWN,
    AV_DISAPPEARED,
)

# --- Тип изменения остатка ---
CH_NONE = "none"
CH_SALE = "sale"  # остаток снизился -> предполагаемая продажа
CH_RESTOCK = "restock"  # остаток вырос -> предполагаемое поступление
CH_UNKNOWN = "unknown"  # количества неизвестны
CH_DISAPPEARED = "disappeared"  # позиция исчезла
CH_FIRST = "first"  # первый снимок

CHANGE_CHOICES = (CH_NONE, CH_SALE, CH_RESTOCK, CH_UNKNOWN, CH_DISAPPEARED, CH_FIRST)

# --- Статусы запуска парсера (п.24 ТЗ) ---
RUN_RUNNING = "running"
RUN_SUCCESS = "success"
RUN_PARTIAL = "partial"  # часть страниц/позиций с ошибками
RUN_ERROR = "error"

# --- Рейтинг спроса (п.9 ТЗ) ---
RATING_A = "A"
RATING_B = "B"
RATING_C = "C"
RATING_D = "D"
RATING_NEW = "NEW"

DEMAND_WINDOWS = (1, 7, 14, 30, 60, 90)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[str]: JSON}  # noqa: RUF012


class Competitor(Base):
    """Конкурент / сайт для мониторинга (п.4, 23 ТЗ)."""

    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    parser_key: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    detail_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    categories: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    runs: Mapped[list[ParserRun]] = relationship(back_populates="competitor")
    offers: Mapped[list[Offer]] = relationship(back_populates="competitor")

    @property
    def last_run(self) -> ParserRun | None:
        return max(self.runs, key=lambda r: r.started_at) if self.runs else None


class ParserRun(Base):
    """Один запуск парсинга сайта (п.24 ТЗ)."""

    __tablename__ = "parser_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competitor_id: Mapped[int] = mapped_column(
        ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=RUN_RUNNING, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    pages_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    offers_written: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    spec_version: Mapped[str] = mapped_column(String(16), default="1", nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    competitor: Mapped[Competitor] = relationship(back_populates="runs")


class Product(Base):
    """Сквозной товар (объединяет одинаковые позиции разных конкурентов, п.17 ТЗ)."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    oem: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    article: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    alt_numbers: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    applicability: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    vanished: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    offers: Mapped[list[Offer]] = relationship(back_populates="product")
    aliases: Mapped[list[ProductAlias]] = relationship(back_populates="product")


class ProductAlias(Base):
    """Алиасы для сопоставления одинаковых товаров (п.17 ТЗ)."""

    __tablename__ = "product_aliases"
    __table_args__ = (UniqueConstraint("alias", name="uq_product_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # oem/article/alt/title

    product: Mapped[Product] = relationship(back_populates="aliases")


class Offer(Base):
    """Позиция товара у конкретного конкурента."""

    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint("product_id", "competitor_id", "url", name="uq_offer_product_site"),
        Index("ix_offers_competitor", "competitor_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False)

    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    seller_article: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(300), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    seen_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    product: Mapped[Product] = relationship(back_populates="offers")
    competitor: Mapped[Competitor] = relationship(back_populates="offers")
    snapshots: Mapped[list[StockSnapshot]] = relationship(back_populates="offer")


class StockSnapshot(Base):
    """Ежедневный снимок состояния позиции. Только добавление — история не перезаписывается
    (п.5, 6, 25 ТЗ)."""

    __tablename__ = "stock_snapshots"
    __table_args__ = (
        UniqueConstraint("offer_id", "snapshot_date", name="uq_snapshot_offer_date"),
        Index("ix_snapshot_product_date", "product_id", "snapshot_date"),
        Index("ix_snapshot_date", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    competitor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    old_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    discount_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    qty: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL = неизвестно
    qty_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    availability: Mapped[str] = mapped_column(String(24), default=AV_UNKNOWN, nullable=False)
    status_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    warehouse: Mapped[str | None] = mapped_column(String(200), nullable=True)
    delivery_time: Mapped[str | None] = mapped_column(String(120), nullable=True)

    delta: Mapped[int | None] = mapped_column(Integer, nullable=True)  # вчера - сегодня
    change_kind: Mapped[str] = mapped_column(String(16), default=CH_FIRST, nullable=False)

    offer: Mapped[Offer] = relationship(back_populates="snapshots")


class ProductDaily(Base):
    """Агрегированный ежедневный снимок по товару (сумма остатков у всех конкурентов,
    цены) — база для расчёта спроса."""

    __tablename__ = "product_daily"
    __table_args__ = (
        UniqueConstraint("product_id", "day", name="uq_product_daily"),
        Index("ix_product_daily_day", "day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)

    qty_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offers_with_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    offers_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    max_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    avg_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    change_kind: Mapped[str] = mapped_column(String(16), default=CH_FIRST, nullable=False)


class ProductStats(Base):
    """Пересчитываемая аналитика по товару: окна спроса, рейтинг, индекс (п.8–12 ТЗ)."""

    __tablename__ = "product_stats"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    days_observed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sale_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    frequency_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)

    sales_1: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sales_7: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sales_14: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sales_30: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sales_60: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sales_90: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    restocks_30: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    avg_daily_sales: Mapped[float] = mapped_column(Numeric(10, 3), default=0, nullable=False)

    competitors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    in_stock_competitors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    min_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    max_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    avg_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    median_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_delta: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_changed_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    rating: Mapped[str] = mapped_column(String(8), default=RATING_NEW, nullable=False, index=True)
    index_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False, index=True)
    index_parts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class IndexWeight(Base):
    """Настраиваемые веса индекса спроса (п.12 ТЗ)."""

    __tablename__ = "index_weights"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(6, 3), default=1.0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DailyReport(Base):
    __tablename__ = "daily_reports"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Setting(Base):
    """Универсальное хранилище настроек (расписание, параметры и т.п.)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


DEFAULT_INDEX_WEIGHTS: list[tuple[str, str, float]] = [
    ("sales_30", "Предполагаемые продажи за 30 дней", 3.0),
    ("sales_7", "Предполагаемые продажи за 7 дней", 2.0),
    ("frequency", "Частота снижения остатка", 2.5),
    ("competitors", "Количество конкурентов с товаром", 1.5),
    ("availability", "Наличие у конкурентов", 1.0),
    ("price_change", "Динамика цены", 0.5),
    ("observation", "Количество дней наблюдения", 1.0),
]

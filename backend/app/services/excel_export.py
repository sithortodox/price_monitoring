from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Competitor,
    Offer,
    Product,
    ProductStats,
    StockSnapshot,
)

DISCLAIMER = (
    "Предполагаемые продажи рассчитаны по снижению остатков у конкурентов "
    "и не являются фактическими данными."
)

HEADER_FILL = PatternFill("solid", fgColor="1F3B57")
HEADER_FONT = Font(color="FFFFFF", bold=True)
THIN = Side(style="thin", color="D0D7DE")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

RATING_FILLS = {
    "A": PatternFill("solid", fgColor="C6EFCE"),
    "B": PatternFill("solid", fgColor="E2EFDA"),
    "C": PatternFill("solid", fgColor="FFEB9C"),
    "D": PatternFill("solid", fgColor="FFC7CE"),
    "NEW": PatternFill("solid", fgColor="DDEBF7"),
}


def export_workbook(db: Session, day: date, history_days: int = 30) -> Workbook:
    """Формирует Excel с 4 листами (п.27 ТЗ)."""
    wb = Workbook()
    wb.remove(wb.active)

    competitors = list(db.execute(select(Competitor).order_by(Competitor.sort_order)).scalars())
    _sheet_summary(wb, db, day, competitors)
    _sheet_demand(wb, db, day)
    _sheet_prices(wb, db, day, competitors)
    _sheet_changes(wb, db, day, history_days, competitors)
    return wb


def export_to_file(db: Session, day: date, path: Path, history_days: int = 30) -> Path:
    wb = export_workbook(db, day, history_days)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _write_header(ws, headers: list[str], row: int = 1) -> None:
    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col, value=title)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def _autosize(ws, max_width: int = 48) -> None:
    for column in ws.columns:
        letter = get_column_letter(column[0].column)
        width = max((len(str(c.value)) for c in column if c.value is not None), default=8)
        ws.column_dimensions[letter].width = min(max(10, width + 2), max_width)


def _sheet_summary(wb: Workbook, db: Session, day: date, competitors: list[Competitor]) -> None:
    ws = wb.create_sheet("Сводка")
    ws["A1"] = f"Мониторинг цен и спроса — {day.strftime('%d.%m.%Y')}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A3"] = DISCLAIMER
    ws["A3"].font = Font(italic=True, color="666666")

    stats = list(db.execute(select(ProductStats)).scalars())
    ratings: dict[str, int] = {}
    for s in stats:
        ratings[s.rating] = ratings.get(s.rating, 0) + 1

    rows = [
        ("Всего товаров", len(stats)),
        ("Продажи A", ratings.get("A", 0)),
        ("Продажи B", ratings.get("B", 0)),
        ("Продажи C", ratings.get("C", 0)),
        ("Продажи D", ratings.get("D", 0)),
        ("Новые / мало наблюдений", ratings.get("NEW", 0)),
        ("Конкурентов в мониторинге", len(competitors)),
    ]
    start = 5
    _write_header(ws, ["Показатель", "Значение"], row=start)
    for offset, (key, value) in enumerate(rows, start=1):
        ws.cell(row=start + offset, column=1, value=key).border = BORDER
        ws.cell(row=start + offset, column=2, value=value).border = BORDER

    competitor_start = start + len(rows) + 3
    _write_header(
        ws,
        ["Сайт", "Парсер", "Активен", "Позиций сегодня", "Статус последнего запуска", "Ошибка"],
        row=competitor_start,
    )
    for i, competitor in enumerate(competitors, start=1):
        offers_today = db.execute(
            select(Offer.id).where(Offer.competitor_id == competitor.id, Offer.seen_on == day)
        ).all()
        run = competitor.last_run
        values = [
            competitor.base_url,
            competitor.parser_key,
            "да" if competitor.enabled else "нет",
            len(offers_today),
            run.status if run else "—",
            (run.error_message or "")[:200] if run else "",
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=competitor_start + i, column=col, value=value)
            cell.border = BORDER
    _autosize(ws)


def _sheet_demand(wb: Workbook, db: Session, day: date) -> None:
    ws = wb.create_sheet("Аналитика спроса")
    headers = [
        "ID",
        "Товар",
        "Бренд",
        "OEM / артикул",
        "Рейтинг",
        "Индекс закупки",
        "Продажи 7д",
        "Продажи 14д",
        "Продажи 30д",
        "Продажи 60д",
        "Продажи 90д",
        "Частота снижения остатка, %",
        "Дней наблюдения",
        "Конкурентов",
        "В наличии у",
        "Мин. цена",
        "Медианная цена",
        "Макс. цена",
        "Δ цены",
        "Пополнений за 30д",
        "Категория",
    ]
    _write_header(ws, headers)
    ws.cell(row=2, column=1, value=DISCLAIMER).font = Font(italic=True, color="666666")

    rows = db.execute(
        select(Product, ProductStats)
        .join(ProductStats, ProductStats.product_id == Product.id)
        .order_by(ProductStats.index_score.desc(), ProductStats.sales_30.desc())
    ).all()
    for i, (product, stats) in enumerate(rows, start=3):
        values = [
            product.id,
            product.title,
            product.brand,
            product.oem or product.article,
            stats.rating,
            float(stats.index_score or 0),
            stats.sales_7,
            stats.sales_14,
            stats.sales_30,
            stats.sales_60,
            stats.sales_90,
            float(stats.frequency_pct or 0),
            stats.days_observed,
            stats.competitors_count,
            stats.in_stock_competitors,
            float(stats.min_price) if stats.min_price is not None else None,
            float(stats.median_price) if stats.median_price is not None else None,
            float(stats.max_price) if stats.max_price is not None else None,
            float(stats.price_delta) if stats.price_delta is not None else None,
            stats.restocks_30,
            product.category,
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=i, column=col, value=value)
            cell.border = BORDER
        rating_cell = ws.cell(row=i, column=5)
        fill = RATING_FILLS.get(str(rating_cell.value))
        if fill:
            rating_cell.fill = fill
    _autosize(ws)


def _sheet_prices(
    wb: Workbook, db: Session, day: date, competitors: list[Competitor]
) -> None:
    ws = wb.create_sheet("Цены конкурентов")
    headers = [
        "ID",
        "Товар",
        "OEM / артикул",
        "Сайт",
        "Цена",
        "Старая цена",
        "Скидка, %",
        "Наличие",
        "Остаток",
        "Текст статуса",
        "Срок поставки",
        "Ссылка",
    ]
    _write_header(ws, headers)

    competitor_names = {c.id: c.name for c in competitors}
    rows = db.execute(
        select(StockSnapshot, Offer, Product)
        .join(Offer, Offer.id == StockSnapshot.offer_id)
        .join(Product, Product.id == StockSnapshot.product_id)
        .where(StockSnapshot.snapshot_date == day)
        .order_by(Product.title, StockSnapshot.competitor_id)
    ).all()
    for i, (snapshot, offer, product) in enumerate(rows, start=2):
        values = [
            product.id,
            product.title,
            product.oem or product.article,
            competitor_names.get(snapshot.competitor_id, snapshot.competitor_id),
            float(snapshot.price) if snapshot.price is not None else None,
            float(snapshot.old_price) if snapshot.old_price is not None else None,
            float(snapshot.discount_pct) if snapshot.discount_pct is not None else None,
            snapshot.availability,
            snapshot.qty,
            snapshot.status_text,
            snapshot.delivery_time,
            offer.url,
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=i, column=col, value=value)
            cell.border = BORDER
            if col == 12 and value:
                cell.hyperlink = str(value)
                cell.font = Font(color="0563C1", underline="single")
    _autosize(ws, max_width=60)


def _sheet_changes(
    wb: Workbook, db: Session, day: date, history_days: int, competitors: list[Competitor]
) -> None:
    ws = wb.create_sheet("Остатки и изменения")
    headers = [
        "Дата",
        "ID",
        "Товар",
        "Сайт",
        "Цена",
        "Остаток",
        "Наличие",
        "Δостатка (вчера − сегодня)",
        "Тип изменения",
        "Комментарий",
    ]
    _write_header(ws, headers)
    ws.cell(row=2, column=1, value=DISCLAIMER).font = Font(italic=True, color="666666")

    start = day - timedelta(days=history_days)
    competitor_names = {c.id: c.name for c in competitors}
    kind_labels = {
        "sale": "продажа (остаток снизился)",
        "restock": "пополнение (остаток вырос)",
        "first": "первое появление",
        "disappeared": "товар исчез",
        "price_changed": "изменение цены",
        "none": "без изменений",
        "unknown": "неизвестно (нет данных о количестве)",
    }
    rows = db.execute(
        select(StockSnapshot, Offer, Product)
        .join(Offer, Offer.id == StockSnapshot.offer_id)
        .join(Product, Product.id == StockSnapshot.product_id)
        .where(
            StockSnapshot.snapshot_date >= start,
            StockSnapshot.snapshot_date <= day,
        )
        .order_by(StockSnapshot.snapshot_date.desc(), Product.title)
    ).all()
    for i, (snapshot, _offer, product) in enumerate(rows, start=3):
        values = [
            snapshot.snapshot_date,
            product.id,
            product.title,
            competitor_names.get(snapshot.competitor_id, snapshot.competitor_id),
            float(snapshot.price) if snapshot.price is not None else None,
            snapshot.qty,
            snapshot.availability,
            snapshot.delta,
            kind_labels.get(snapshot.change_kind, snapshot.change_kind),
            snapshot.qty_text,
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=i, column=col, value=value)
            cell.border = BORDER
            if col == 1:
                cell.number_format = "DD.MM.YYYY"
    _autosize(ws, max_width=60)


def summary_payload(db: Session, day: date) -> dict[str, Any]:
    """Небольшая сводка для ответа API после экспорта."""
    stats = list(db.execute(select(ProductStats)).scalars())
    return {
        "day": day.isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "products": len(stats),
        "sheets": ["Сводка", "Аналитика спроса", "Цены конкурентов", "Остатки и изменения"],
    }

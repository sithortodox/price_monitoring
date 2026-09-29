from __future__ import annotations

import re
import unicodedata

from ..models import (
    AV_IN_STOCK,
    AV_MANY,
    AV_ON_ORDER,
    AV_OUT_OF_STOCK,
    AV_UNKNOWN,
)

NBSP = "\xa0"
_RUBLES = ("₽", "руб", "р.", "rub", "рублей", "RUB")

_PRICE_CLEAN = re.compile(r"[^\d,.\-]")
_INT_RE = re.compile(r"\d+")

_OUT_WORDS = ("нет в наличии", "нету в наличии", "отсутствует", "отсутствуют", "не в наличии", "распродан")
_ORDER_WORDS = ("под заказ", "по заказу", "предзаказ", "под заказом")
_MANY_WORDS = ("много", "масса", "большое количество", "достаточно")
_IN_WORDS = ("в наличии", "есть на складе", "на складе", "в наличии на складе", "доступен", "available", "instock")

_QTY_PATTERNS = (
    re.compile(r"(?:остаток|остатки|в наличии|на складе|доступно|количество)\s*[:\-–]?\s*(\d{1,7})", re.I),
    re.compile(r"(\d{1,7})\s*(?:шт(?:\.|ук)?|pcs|ед\.?|единиц)", re.I),
    re.compile(r"(\d{1,7})\s+(?:в наличии|на складе)", re.I),
    re.compile(r"qty\s*[:=]?\s*(\d{1,7})", re.I),
)


def parse_price(raw: str | float | int | None) -> float | None:
    """Разбирает цену вида «6 100 ₽», «4,095 р.», «12 900.50», «1 559 руб.»."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)

    text = str(raw).replace(NBSP, " ").strip()
    if not text:
        return None
    text = re.sub(r"(?i)(" + "|".join(re.escape(r) for r in _RUBLES) + r")", "", text)
    text = _PRICE_CLEAN.sub("", text).strip(" ,.-")
    if not text:
        return None

    has_dot = "." in text
    has_comma = "," in text

    if has_dot and has_comma:
        # последний разделитель — десятичный
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        head, _, tail = text.rpartition(",")
        if len(tail) == 3 and head and head.lstrip("-").isdigit():
            text = text.replace(",", "")  # 4,095 -> 4095 (тысячи)
        else:
            text = text.replace(",", ".")
    elif has_dot:
        head, _, tail = text.rpartition(".")
        if len(tail) == 3 and head and head.lstrip("-").isdigit() and len(head.lstrip("-")) <= 3:
            text = text.replace(".", "")  # 1.559 -> 1559 (тысячи в некоторых выгрузках)
        else:
            text = text.replace(".", "", text.count(".") - 1)

    if not re.fullmatch(r"-?\d+(\.\d+)?", text):
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if value <= 0 or value > 10_000_000:
        return None
    return value


def normalize_key(value: str | None) -> str:
    """Нормализация артикула/OEM: верхний регистр, ё->е, только буквы и цифры."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).upper().replace("Ё", "Е")
    text = re.sub(r"[^0-9A-ZА-Я]+", "", text)
    return text


def parse_quantity(raw: str | int | None) -> tuple[int | None, str | None, str]:
    """
    Возвращает (количество, исходный текст, статус наличия).

    Правила п.16 ТЗ:
      «Много»            -> количество неизвестно, статус many
      «В наличии» без qty-> наличие есть, количества нет
      «Под заказ»        -> остаток неизвестен
      «Нет в наличии»    -> 0
      число              -> число
    """
    if raw is None:
        return None, None, AV_UNKNOWN

    if isinstance(raw, int):
        return (raw if raw > 0 else 0), str(raw), (AV_IN_STOCK if raw > 0 else AV_OUT_OF_STOCK)

    text = re.sub(r"\s+", " ", str(raw).replace(NBSP, " ")).strip()
    if not text:
        return None, None, AV_UNKNOWN
    low = text.lower()

    if any(w in low for w in _OUT_WORDS):
        return 0, text, AV_OUT_OF_STOCK
    if any(w in low for w in _ORDER_WORDS):
        return None, text, AV_ON_ORDER

    for pattern in _QTY_PATTERNS:
        match = pattern.search(text)
        if match:
            qty = int(match.group(1))
            if qty == 0 and not any(w in low for w in _IN_WORDS):
                return 0, text, AV_OUT_OF_STOCK
            return qty, text, AV_IN_STOCK

    if any(w in low for w in _IN_WORDS) or low in {"yes", "true", "есть"}:
        return None, text, AV_IN_STOCK

    if any(w in low for w in _MANY_WORDS):
        return None, text, AV_MANY

    number = _INT_RE.search(text)
    if number and len(text) <= 12:
        return int(number.group(0)), text, AV_IN_STOCK

    return None, text, AV_UNKNOWN


_AVAIL_FROM_SCHEMA = {
    "instock": AV_IN_STOCK,
    "outofstock": AV_OUT_OF_STOCK,
    " preorder": AV_ON_ORDER,
    "preorder": AV_ON_ORDER,
    "limitedavailability": AV_IN_STOCK,
    "onlineonly": AV_IN_STOCK,
    "instoreonly": AV_IN_STOCK,
}


def availability_from_schema(url_or_name: str | None) -> str | None:
    if not url_or_name:
        return None
    token = url_or_name.rstrip("/").rsplit("/", 1)[-1].lower()
    return _AVAIL_FROM_SCHEMA.get(token.replace(" ", ""))


def old_price_and_discount(price: float | None, old_price: float | None) -> tuple[float | None, float | None]:
    if price and old_price and old_price > price:
        return old_price, round((old_price - price) / old_price * 100, 1)
    return (old_price if old_price else None), None


def extract_numbers(text: str | None, limit: int = 8) -> list[str]:
    """Достаёт кросс-номера из скобок/перечислений: «(LEO100183A, 612600030033)»."""
    if not text:
        return []
    out: list[str] = []
    for chunk in re.split(r"[;,/|]", text):
        candidate = normalize_key(chunk.strip(" ()[]"))
        if 4 <= len(candidate) <= 40 and re.search(r"\d", candidate) and candidate not in out:
            out.append(candidate)
        if len(out) >= limit:
            break
    return out

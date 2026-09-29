from __future__ import annotations

from app.models import AV_IN_STOCK, AV_MANY, AV_ON_ORDER, AV_OUT_OF_STOCK, AV_UNKNOWN
from app.parsers.normalize import (
    availability_from_schema,
    extract_numbers,
    normalize_key,
    old_price_and_discount,
    parse_price,
    parse_quantity,
)


def test_parse_price_thousands_comma():
    assert parse_price("4,095") == 4095.0
    assert parse_price("1,559") == 1559.0


def test_parse_price_decimal():
    assert parse_price("12 900.50") == 12900.5
    assert parse_price("12,90") == 12.9
    assert parse_price("1.500,50") == 1500.5


def test_parse_price_currency_and_junk():
    assert parse_price("6 100 ₽") == 6100.0
    assert parse_price("1 559 руб.") == 1559.0
    assert parse_price("1 559 р.") == 1559.0
    assert parse_price("Узнать цену") is None
    assert parse_price(None) is None


def test_parse_price_rejects_out_of_range():
    assert parse_price("0") is None
    assert parse_price("99 999 999") is None


def test_normalize_key():
    assert normalize_key("leo 100-183a") == "LEO100183A"
    assert normalize_key("612600030033") == "612600030033"
    assert normalize_key("деталь") == "ДЕТАЛЬ"
    assert normalize_key(None) == ""


def test_quantity_rules_from_tz():
    assert parse_quantity("Много") == (None, "Много", AV_MANY)
    assert parse_quantity("Под заказ") == (None, "Под заказ", AV_ON_ORDER)
    assert parse_quantity("Нет в наличии") == (0, "Нет в наличии", AV_OUT_OF_STOCK)
    assert parse_quantity("12 шт.") == (12, "12 шт.", AV_IN_STOCK)
    assert parse_quantity("В наличии") == (None, "В наличии", AV_IN_STOCK)
    assert parse_quantity(None) == (None, None, AV_UNKNOWN)
    assert parse_quantity(5) == (5, "5", AV_IN_STOCK)
    assert parse_quantity(0) == (0, "0", AV_OUT_OF_STOCK)


def test_quantity_warehouse_text():
    qty, text, status = parse_quantity("Остаток: 7 шт., склад Москва")
    assert qty == 7
    assert status == AV_IN_STOCK
    assert "Москва" in text


def test_availability_from_schema():
    assert availability_from_schema("https://schema.org/InStock") == AV_IN_STOCK
    assert availability_from_schema("https://schema.org/OutOfStock") == AV_OUT_OF_STOCK
    assert availability_from_schema("https://schema.org/PreOrder") == AV_ON_ORDER
    assert availability_from_schema(None) is None


def test_old_price_and_discount():
    old, pct = old_price_and_discount(800.0, 1000.0)
    assert old == 1000.0
    assert pct == 20.0
    assert old_price_and_discount(1000.0, 800.0) == (800.0, None)


def test_extract_numbers():
    got = extract_numbers("(LEO100183A, 612600030033) / 1234567")
    assert "LEO100183A" in got
    assert "612600030033" in got
    assert extract_numbers("") == []


def test_quantity_with_number_before_word():
    """autoopt пишет остаток как «113 в наличии» — слово стоит после числа."""
    assert parse_quantity("Код для заказа: 537513 Артикул: 612630050011 РЗ 175,00 ₽ В корзину 113 в наличии На складах :")[:1] == (113,)
    assert parse_quantity("В корзину 597 шт. 4 дн.")[:1] == (597,)
    assert parse_quantity("В корзину Нет в наличии") == (0, "В корзину Нет в наличии", "out_of_stock")

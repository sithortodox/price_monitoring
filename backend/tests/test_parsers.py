from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers.registry import PARSER_CLASSES

FIXTURES = Path(__file__).parent / "fixtures"

CASES = [
    ("aac86", "aac86.html", 10, True),
    ("amrparts", "amr_catalog.html", 5, False),
    ("autoopt", "autoopt_catalog.html", 10, False),
    ("dcc", "dcc.html", 5, True),
    ("glavmeh", "glavmeh.html", 5, True),
    ("relines", "relines.html", 5, True),
    ("shparts", "sh_folder.html", 5, True),
    ("stugs", "stugs.html", 5, True),
    ("transek", "transek.html", 5, True),
    ("truckdrive", "truckdrive_leaf.html", 2, True),
]


@pytest.mark.parametrize("key,filename,min_offers,require_price", CASES)
def test_list_page_parses_saved_html(key, filename, min_offers, require_price):
    path = FIXTURES / filename
    if not path.exists():
        pytest.skip(f"нет фикстуры {filename}")
    cls = PARSER_CLASSES[key]
    parser = cls(fetcher=None, browser=None)
    offers, next_url = parser.parse_list_page(path.read_text(errors="replace"), "https://example.com/list")

    assert len(offers) >= min_offers, f"{key}: найдено {len(offers)} позиций"
    assert next_url or len(offers) > 0

    first = offers[0]
    assert first.url.startswith("http")
    assert first.title
    assert first.availability in {"in_stock", "out_of_stock", "on_order", "many", "unknown"}
    if require_price:
        assert first.price is not None and first.price > 0, f"{key}: цена не распарсена"
    articles = [o.seller_article for o in offers if o.seller_article]
    assert len(articles) >= len(offers) // 2, f"{key}: артикул найден не у половины позиций"


def test_registry_covers_all_eleven_sites():
    assert len(PARSER_CLASSES) == 11
    for cls in PARSER_CLASSES.values():
        assert cls.key
        assert cls.site_name
        assert cls.default_urls
        assert cls.default_urls[0].startswith("http")


def test_autoopt_brand_comes_from_popup_title_not_description():
    """В контейнере бренда лежит попап с длинным описанием — марка берётся из заголовка."""
    html = (FIXTURES / "autoopt_catalog.html").read_text(errors="replace")
    parser = PARSER_CLASSES["autoopt"](fetcher=None, browser=None)
    offers, _ = parser.parse_list_page(html, "https://www.autoopt.ru/catalog/list")

    assert offers
    brands = {o.brand for o in offers}
    assert "SHACMAN" in brands
    assert all(not b or len(b) <= 60 for b in brands), f"в марку попало описание: {brands}"


def test_truckdrive_group_page_yields_no_offers():
    cls = PARSER_CLASSES["truckdrive"]
    parser = cls(fetcher=None, browser=None)
    html = (FIXTURES / "truckdrive_group.html").read_text()
    offers, next_url = parser.parse_list_page(html, "https://truckdrive.ru/catalog/")

    assert offers == []
    assert next_url is None


def test_truckdrive_expand_start_urls_finds_leaf_groups():
    group_html = (FIXTURES / "truckdrive_group.html").read_text()
    leaf_html = (FIXTURES / "truckdrive_leaf.html").read_text()
    parent = "https://truckdrive.ru/catalog/?search_cataloggroup=katalog-zapchasti-dlya-gruzovikov-shacman"
    # expand запрашивает каждую группу сразу с catalog_perpage=500
    pages = {
        parent + "&catalog_perpage=500": group_html,
        "https://truckdrive.ru/catalog/?search_cataloggroup=katalog-zapchasti-dlya-shacman-x3000"
        + "&catalog_perpage=500": "",
        "https://truckdrive.ru/catalog/?search_cataloggroup=katalog-filtri-gruzovikov-shacman-x3000"
        + "&catalog_perpage=500": leaf_html,
        "https://truckdrive.ru/catalog/?search_cataloggroup=katalog-tormoza-gruzovikov-shacman-x6000"
        + "&catalog_perpage=500": leaf_html,
    }
    parser = PARSER_CLASSES["truckdrive"](fetcher=None, browser=object())
    parser._get = lambda url: pages.get(url, "")  # type: ignore[method-assign]

    urls = parser.expand_start_urls([parent])

    assert urls == [
        "https://truckdrive.ru/catalog/?search_cataloggroup=katalog-filtri-gruzovikov-shacman-x3000"
        "&catalog_perpage=500",
        "https://truckdrive.ru/catalog/?search_cataloggroup=katalog-tormoza-gruzovikov-shacman-x6000"
        "&catalog_perpage=500",
    ]


def test_truckdrive_expand_without_browser_keeps_urls():
    parent = PARSER_CLASSES["truckdrive"].default_urls[0]
    parser = PARSER_CLASSES["truckdrive"](fetcher=None, browser=None)

    assert parser.expand_start_urls([parent]) == [parent]


def test_truckdrive_next_url_uses_catalog_page_param():
    parser = PARSER_CLASSES["truckdrive"]
    url = parser._with_perpage("https://truckdrive.ru/catalog/?search_cataloggroup=shacman-x3000")

    assert "catalog_perpage=500" in url
    assert parser._next_url(url, 499) is None  # меньше лимита — страниц больше нет
    next_page = parser._next_url(url, 500)  # страница заполнена целиком — пробуем следующую
    assert next_page is not None and "catalog_page=2" in next_page
    url24 = "https://truckdrive.ru/catalog/?search_cataloggroup=shacman-x3000&catalog_perpage=24"
    assert parser._next_url(url24, 10) is None
    assert "catalog_page=2" in (parser._next_url(url24, 24) or "")


def test_missing_pagination_page_is_warning_not_error(competitor):
    from typing import ClassVar

    from app.parsers.base import BaseSiteParser, RawOffer

    class Stub(BaseSiteParser):
        key = "stub"
        site_name = "Stub"
        default_urls: ClassVar[list[str]] = ["https://x.example/l"]

        def _get(self, url: str) -> str:
            self.calls = getattr(self, "calls", 0) + 1
            return "OFFER NEXT" if self.calls == 1 else ""

        def parse_list_page(self, html, page_url):
            if "OFFER" not in html:
                return [], None
            offer = RawOffer(url=page_url + "/o1", title="Деталь")
            return [offer], page_url + "?page=2"

    result = Stub(fetcher=None, browser=None).parse(competitor)

    assert len(result.offers) == 1
    assert result.errors == []  # конец пагинации — не ошибка
    assert any("не загрузилась" in w for w in result.warnings)


def test_first_page_failure_is_error(competitor):
    from typing import ClassVar

    from app.parsers.base import BaseSiteParser, RawOffer

    class Stub(BaseSiteParser):
        key = "stub"
        site_name = "Stub"
        default_urls: ClassVar[list[str]] = ["https://x.example/l"]

        def _get(self, url: str) -> str:
            return ""

        def parse_list_page(self, html, page_url):
            return [RawOffer(url=page_url, title="Деталь")], None

    result = Stub(fetcher=None, browser=None).parse(competitor)

    assert result.offers == []
    assert any("Не удалось загрузить" in e for e in result.errors)


_AUTOOPT_CARD_TMPL = """
<div class="n-catalog-item relative grid-item n-catalog-item__product">
  <a class="actions name-popover n-catalog-item__name-link" href="/catalog/ts123-shacman-6180030019">Болт шатуна WP12</a>
  <div class="n-catalog-item__brand">
    <a class="actions brand-popover" href="#autoopt-popup">
      <span class="popup-brand__title"><span>SHACMAN</span></span>
    </a>
  </div>
  <div class="n-catalog-item__price-count">
    Код для заказа: TS37334296 Артикул: 6180030019
    <span class="price-item">4 105,00 ₽</span>
    <a class="link-color fake" href="#">РЗ</a>
    {status} На складах :
  </div>
</div>
"""


def _autoopt_offers(status: str):
    html = "<html><body>" + _AUTOOPT_CARD_TMPL.format(status=status) + "</body></html>"
    parser = PARSER_CLASSES["autoopt"](fetcher=None, browser=None)
    offers, _ = parser.parse_list_page(html, "https://www.autoopt.ru/catalog/list")
    return offers


def test_autoopt_qty_parsed_from_price_block_not_from_retail_link():
    """Узел .link-color.fake на оптовых карточках содержит «РЗ» — остаток берём из блока цены."""
    offers = _autoopt_offers("В корзину 113 в наличии")

    assert len(offers) == 1
    offer = offers[0]
    assert offer.qty == 113
    assert offer.availability == "in_stock"
    assert offer.price == 4105.0
    assert offer.brand == "SHACMAN"


def test_autoopt_out_of_stock_and_on_order_statuses():
    out = _autoopt_offers("В корзину Нет в наличии")[0]
    assert (out.qty, out.availability) == (0, "out_of_stock")

    order = _autoopt_offers("В корзину Под заказ")[0]
    assert (order.qty, order.availability) == (None, "on_order")


def test_shparts_card_without_stock_flag_uses_cart_button():
    html = """
    <form class="shop2-product-item product-item" method="post">
      <div class="product-item__inner">
        <div class="gr-product-name"><a href="/magazin/product/kabina-dayun-x120">Кабина DAYUN X120</a></div>
        <div class="product-price"><div class="price-current price_on_request"><strong>Цена по запросу</strong></div></div>
        <button class="gr-btn type-2 notavailable" type="submit"><span> Нет в наличии </span></button>
      </div>
    </form>
    """
    parser = PARSER_CLASSES["shparts"](fetcher=None, browser=None)
    offers, _ = parser.parse_list_page(html, "https://sh-parts.ru/magazin/folder/1")

    assert len(offers) == 1
    offer = offers[0]
    assert offer.availability == "out_of_stock"
    assert offer.qty == 0
    assert offer.status_text == "Нет в наличии"
    assert offer.price is None

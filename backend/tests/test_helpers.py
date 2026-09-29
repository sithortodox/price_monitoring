from __future__ import annotations

from app.parsers.helpers import current_page_number, find_next_page


def test_next_page_follows_explicit_link():
    html = '<div class="pagination"><a href="/catalog/?PAGEN_1=2">2</a></div>'
    url = "https://x.example/catalog/?PAGEN_1=1"

    assert find_next_page(html, url) == "https://x.example/catalog/?PAGEN_1=2"


def test_last_page_without_next_number_returns_none():
    """Раньше страница «выдумывалась» по наличию параметра в URL и давала 404."""
    html = '<div class="pagination"><a href="/catalog/?PAGEN_1=5">5</a></div>'
    url = "https://x.example/catalog/?PAGEN_1=5"

    assert find_next_page(html, url) is None


def test_rel_next_link_is_used():
    html = '<a rel="next" href="/catalog/page-2">Далее</a>'
    url = "https://x.example/catalog/"

    assert find_next_page(html, url) == "https://x.example/catalog/page-2"


def test_next_label_link_is_used():
    html = '<a class="page-link" href="/list?p=2">следующая</a>'
    url = "https://x.example/list"

    assert find_next_page(html, url) == "https://x.example/list?p=2"


def test_shparts_offset_pagination():
    html = '<a class="page-link" href="/magazin/folder/123/p/1">2</a>'
    url = "https://sh-parts.ru/magazin/folder/123/p/0"

    assert current_page_number(url) == 1
    assert find_next_page(html, url) == "https://sh-parts.ru/magazin/folder/123/p/1"


def test_no_pagination_markup_returns_none():
    assert find_next_page("<div>нет пагинации</div>", "https://x.example/list") is None


def test_extract_qty_from_detail_finds_stock_block():
    from app.parsers.helpers import extract_qty_from_detail

    html = '<html><body><div id="stock">В наличии 12 шт.</div></body></html>'
    qty, qty_text, avail, _warehouse = extract_qty_from_detail(html)

    assert qty == 12
    assert avail == "in_stock"
    assert "12" in qty_text


def test_extract_qty_from_detail_out_of_stock():
    from app.parsers.helpers import extract_qty_from_detail

    qty, _qty_text, avail, _warehouse = extract_qty_from_detail(
        '<html><body><div class="product-stock">Нет в наличии</div></body></html>'
    )

    assert (qty, avail) == (0, "out_of_stock")


def test_extract_qty_from_detail_reads_schema_meta():
    from app.parsers.helpers import extract_qty_from_detail

    html = '<html><head><meta itemprop="availability" content="https://schema.org/PreOrder"/></head><body></body></html>'
    qty, _qty_text, avail, _warehouse = extract_qty_from_detail(html)

    assert qty is None
    assert avail == "on_order"

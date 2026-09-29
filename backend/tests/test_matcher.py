from __future__ import annotations

from app.models import Competitor, Product, ProductAlias
from app.parsers.base import RawOffer
from app.services.matcher import ProductMatcher


def _offer(url: str, title: str, **kwargs) -> RawOffer:
    return RawOffer(url=url, title=title, **kwargs)


def test_same_oem_from_different_sites_is_one_product(db, competitor):
    other = Competitor(
        name="Второй сайт",
        domain="two.example",
        base_url="https://two.example/",
        parser_key="dcc",
        config={"urls": ["https://two.example/"]},
        sort_order=2,
    )
    db.add(other)
    db.commit()

    matcher = ProductMatcher(db)
    first = matcher.match(
        _offer(
            "https://test.example/p/1",
            "Колодки тормозные передние LEO100183A",
            oem="LEO 100183 A",
            brand="LEOFAR",
        )
    )
    second = matcher.match(
        _offer(
            "https://two.example/item/9",
            "Колодки тормозные LEO100183A",
            oem="leo100183a",
        )
    )
    db.commit()

    assert first.id == second.id
    assert db.query(Product).count() == 1
    aliases = {a.alias for a in db.query(ProductAlias).all()}
    assert "LEO100183A" in aliases


def test_different_articles_create_separate_products(db):
    matcher = ProductMatcher(db)
    a = matcher.match(_offer("https://test.example/a", "Фильтр масляный 110901", oem="110901"))
    b = matcher.match(_offer("https://test.example/b", "Фильтр масляный 110902", oem="110902"))
    db.commit()
    assert a.id != b.id


def test_title_fallback_when_no_article(db):
    matcher = ProductMatcher(db)
    a = matcher.match(
        _offer("https://test.example/x", "Корпус редуктора моста заднего Shaanxi")
    )
    b = matcher.match(
        _offer("https://test.example/y", "Корпус редуктора моста заднего Shaanxi")
    )
    db.commit()
    assert a.id == b.id
    assert db.query(Product).count() == 1


def test_alt_numbers_merge(db):
    matcher = ProductMatcher(db)
    matcher.match(
        _offer(
            "https://test.example/1",
            "Деталь A",
            oem="AAAA1111",
            alt_numbers=["BBBB2222"],
        )
    )
    product = matcher.match(
        _offer(
            "https://other.example/1",
            "Деталь A",
            oem="AAAA1111",
            alt_numbers=["CCCC3333"],
        )
    )
    db.commit()
    assert set(product.alt_numbers) == {"BBBB2222", "CCCC3333"}
    assert db.query(Product).count() == 1


def test_long_site_fields_are_clipped_to_column_limits(db):
    """Данные сайтов бывают длиннее схемы — обрезаем, чтобы INSERT не падал."""
    matcher = ProductMatcher(db)
    product = matcher.match(
        _offer(
            "https://test.example/long",
            "Болт шатунный " + "х" * 600,
            oem="X" * 200,
            seller_article="A" * 250,
            brand="SHACMAN - " + "р" * 300,
            manufacturer="Производитель " + "м" * 300,
            applicability="Применимость " + "п" * 600,
            category="Категория " + "к" * 400,
        )
    )
    db.commit()

    assert len(product.title) == 500
    assert len(product.match_key) <= 128
    assert len(product.brand or "") <= 200
    assert len(product.manufacturer or "") <= 200
    assert len(product.oem or "") <= 128
    assert len(product.article or "") <= 128
    assert len(product.applicability or "") <= 500
    assert len(product.category or "") <= 300
    assert all(len(a.alias) <= 128 for a in product.aliases)

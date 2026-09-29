from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

_PAGE_PARAMS = ("page", "PAGEN_1", "PAGEN_2", "p", "curPos", "page_num", "PAGEN")


def current_page_number(url: str, default: int = 1) -> int:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in _PAGE_PARAMS:
        if key in query:
            try:
                value = int(query[key][0])
            except (ValueError, TypeError):
                continue
            return value if key != "curPos" else max(1, value // 50 + 1)
    match = re.search(r"/p/(\d+)", parsed.path)
    if match:
        return int(match.group(1)) + 1
    return default


def with_page_number(url: str, page: int) -> str:
    """Собирает URL страницы каталога с учётом используемого сайтом параметра."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    path = parsed.path

    if "/p/" in path:  # sh-parts: /folder/123/p/1 (0-based)
        path = re.sub(r"/p/\d+", "", path)
        if page > 1:
            path = f"{path.rstrip('/')}/p/{page - 1}"
        return urlunparse(parsed._replace(path=path, query=""))

    for key in ("PAGEN_1", "page", "curPos", "p"):
        if key in query or key.lower() in {k.lower() for k in query}:
            actual = next(k for k in query if k.lower() == key.lower())
            query.pop(actual, None)
            if page > 1:
                query[actual] = [str(page if key != "curPos" else (page - 1) * 50)]
            break
    else:
        if page > 1:
            query["page"] = [str(page)]

    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def find_next_page(html: str, current_url: str) -> str | None:
    """Универсальный поиск ссылки на следующую страницу каталога."""
    soup = BeautifulSoup(html, "lxml")
    base_number = current_page_number(current_url)

    next_anchor = soup.select_one(
        "a[rel=next], a.pagination-next, a.page-next, .pager-next a, a[class*=next], a[class*=Next]"
    )
    if next_anchor and next_anchor.get("href"):
        return urljoin(current_url, next_anchor["href"])

    for anchor in soup.find_all("a", href=True):
        label = anchor.get_text(" ", strip=True).lower()
        if label in {"след.", "следующая", "далее", "дальше", "next", "→", ">", "вперёд"}:
            return urljoin(current_url, anchor["href"])

    # запасной вариант — только если в разметке есть явная ссылка на номер страницы N+1:
    # иначе последняя страница давала бы 404/пустой ответ при «выдуманной» пагинации
    next_number = base_number + 1
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if re.search(rf"/p/{base_number}(?:[/?#]|$)", href):  # sh-parts: /p/N (0-based)
            return urljoin(current_url, href)
        for key in _PAGE_PARAMS:
            if key == "curPos":
                continue  # смещения, а не номера страниц — не угадываем
            if re.search(rf"[?&]{key}={next_number}(?:[&#]|$)", href):
                return urljoin(current_url, href)
    return None


def first_or_none(nodes: object) -> object | None:
    try:
        return next(iter(nodes))  # type: ignore[arg-type]
    except StopIteration:
        return None


def clean(text: str | None, limit: int = 500) -> str | None:
    if not text:
        return None
    value = re.sub(r"\s+", " ", text).strip()
    if not value:
        return None
    return value[:limit]


_QTY_HINT = re.compile(r"(stock|qty|count|ostat|nalich|avail|quantity|sklad)", re.I)


def extract_qty_from_detail(html: str) -> tuple[int | None, str | None, str, str | None]:
    """Универсальное извлечение остатка/наличия со страницы товара.

    Ищет блоки с типовыми классами (stock/qty/остаток/наличие) и прогоняет их
    через общий разбор количества. Возвращает (qty, qty_text, availability, warehouse).
    """
    from ..models import AV_UNKNOWN
    from .normalize import availability_from_schema, parse_quantity

    soup = BeautifulSoup(html, "lxml")
    warehouse = None

    for meta in soup.select('meta[itemprop="availability"], link[itemprop="availability"]'):
        token = meta.get("content") or meta.get("href")
        parsed = availability_from_schema(token)
        if parsed and parsed != "unknown":
            return None, None, parsed, warehouse

    candidates: list[str] = []
    for node in soup.find_all(class_=_QTY_HINT):
        text = clean(node.get_text(" ", strip=True))
        if text and len(text) < 200:
            candidates.append(text)
    for node in soup.find_all(id=_QTY_HINT):
        text = clean(node.get_text(" ", strip=True))
        if text and len(text) < 200:
            candidates.append(text)

    for text in candidates:
        qty, qty_text, availability = parse_quantity(text)
        if availability != AV_UNKNOWN and (qty is not None or availability != "unknown"):
            return qty, qty_text, availability, warehouse

    body_text = clean(soup.get_text(" ", strip=True), 4000) or ""
    qty, qty_text, availability = parse_quantity(body_text)
    if availability != "unknown":
        return qty, qty_text, availability, warehouse
    return None, None, AV_UNKNOWN, warehouse

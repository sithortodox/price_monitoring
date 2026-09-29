from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Competitor
from .parsers.registry import PARSER_CLASSES

log = logging.getLogger("seed")

# Домены и человекочитаемые названия для 11 конкурентов из ТЗ
SEED_OVERRIDES: dict[str, dict[str, object]] = {
    "aac86": {"name": "АвтоАгрегатЦентр (aac86.ru)"},
    "amrparts": {"name": "Автомагистраль (amrparts.ru)"},
    "autoopt": {"name": "Автоопт (autoopt.ru)"},
    "autopiter": {"name": "АвтоПитер (autopiter.ru)"},
    "dcc": {"name": "1 Детали (1dcc.ru)"},
    "glavmeh": {"name": "ГлавМех (главмех.рф)"},
    "relines": {"name": "Релинес (relines.ru)"},
    "shparts": {"name": "SH Parts (sh-parts.ru)"},
    "stugs": {"name": "Стугс (stugs.ru)"},
    "transek": {"name": "ТрансЭк (trans-ek.ru)"},
    "truckdrive": {"name": "TruckDrive (truckdrive.ru)"},
}


def seed_competitors(db: Session) -> int:
    """Создаёт конкурентов из реестра парсеров, если таблица пуста (п.23 ТЗ)."""
    existing = db.execute(select(func.count(Competitor.id))).scalar() or 0
    if existing:
        return 0

    created = 0
    for order, key in enumerate(sorted(PARSER_CLASSES), start=1):
        cls = PARSER_CLASSES[key]
        override = SEED_OVERRIDES.get(key, {})
        urls = list(cls.default_urls)
        base_url = urls[0] if urls else ""
        domain = base_url.split("//")[-1].split("/")[0] if base_url else key
        db.add(
            Competitor(
                name=str(override.get("name") or cls.site_name or key),
                domain=domain,
                base_url=base_url,
                parser_key=key,
                enabled=True,
                detail_enabled=cls.detail_enabled_by_default,
                config={"urls": urls},
                categories=[],
                sort_order=order,
                note="Создано автоматически из реестра парсеров",
            )
        )
        created += 1
    db.commit()
    log.info("seeded %s competitors", created)
    return created


def reset_urls_from_registry(db: Session) -> int:
    """Подставляет актуальные URL каталогов из парсеров в пустые config["urls"]."""
    updated = 0
    for competitor in db.execute(select(Competitor)).scalars():
        cls = PARSER_CLASSES.get(competitor.parser_key)
        if cls is None:
            continue
        urls = competitor.config.get("urls") or []
        if not urls and cls.default_urls:
            competitor.config = {**competitor.config, "urls": list(cls.default_urls)}
            updated += 1
    db.commit()
    return updated

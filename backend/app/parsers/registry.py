from __future__ import annotations

from .base import BaseSiteParser
from .sites.aac86 import Aac86Parser
from .sites.amrparts import AmrpartsParser
from .sites.autoopt import AutooptParser
from .sites.autopiter import AutopiterParser
from .sites.dcc import DccParser
from .sites.glavmeh import GlavmehParser
from .sites.relines import RelinesParser
from .sites.shparts import ShpartsParser
from .sites.stugs import StugsParser
from .sites.transek import TransekParser
from .sites.truckdrive import TruckdriveParser

PARSER_CLASSES: dict[str, type[BaseSiteParser]] = {
    cls.key: cls
    for cls in (
        Aac86Parser,
        AmrpartsParser,
        AutooptParser,
        AutopiterParser,
        DccParser,
        GlavmehParser,
        RelinesParser,
        ShpartsParser,
        StugsParser,
        TransekParser,
        TruckdriveParser,
    )
}


def available_parsers() -> list[dict[str, str]]:
    return [
        {
            "key": cls.key,
            "name": cls.site_name,
            "urls": ", ".join(cls.default_urls),
            "use_browser": str(cls.use_browser),
        }
        for cls in PARSER_CLASSES.values()
    ]


def get_parser_class(key: str) -> type[BaseSiteParser]:
    if key not in PARSER_CLASSES:
        raise KeyError(f"Неизвестный парсер: {key}")
    return PARSER_CLASSES[key]

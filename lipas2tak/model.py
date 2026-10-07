"""Sisäinen tietomalli: kaikki lähteet normalisoidaan näiksi."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .geo import Coord, Line


@dataclass
class Localized:
    fi: str = ""
    en: str = ""

    def get(self, lang: str) -> str:
        v = getattr(self, lang, "") or ""
        return v or self.fi or self.en

    @classmethod
    def from_any(cls, v) -> "Localized":
        if v is None:
            return cls()
        if isinstance(v, str):
            return cls(fi=v)
        if isinstance(v, dict):
            return cls(fi=v.get("fi") or "", en=v.get("en") or "")
        return cls(fi=str(v))


@dataclass
class Feature:
    """Yksi merkki tai reitti."""

    uid: str                     # pysyvä CoT-UID, esim. lipas-509474
    source: str                  # lipas | loi | osm
    source_id: str
    kind: str                    # types.yaml:n kind
    name: Localized
    point: Optional[Coord] = None            # merkit
    lines: list[Line] = field(default_factory=list)  # reitit (yksinkertaistettu)
    description: Localized = field(default_factory=Localized)
    services: list[str] = field(default_factory=list)   # palveluavaimet, esim. toilet
    marking: Localized = field(default_factory=Localized)  # reitin maastomerkintä
    accessibility: Localized = field(default_factory=Localized)
    length_km: Optional[float] = None
    www: str = ""
    admin: str = ""
    status: str = "active"
    city_code: Optional[int] = None
    updated: str = ""
    # Täytetään rikastusvaiheessa
    areas: list[str] = field(default_factory=list)    # alueavaimet, esim. kansallispuistot/nuuksio
    region: Optional[str] = None                      # maakunta-avain, esim. maakunnat/uusimaa

    @property
    def is_route(self) -> bool:
        return bool(self.lines)

    def all_coords(self) -> list[Coord]:
        if self.point:
            return [self.point]
        return [c for l in self.lines for c in l]


@dataclass
class AreaDef:
    """Kansallispuisto, erämaa-alue tai maakunta."""

    slug: str            # esim. nuuksio, uusimaa
    category: str        # kansallispuistot | eramaat | maakunnat ...
    name: Localized
    tag: str             # hashtag ilman #
    geometry: dict
    buffer_m: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.category}/{self.slug}"

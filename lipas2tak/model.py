"""Internal data model: all sources are normalised to these."""
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
    """A single marker or route."""

    uid: str                     # stable CoT UID, e.g. lipas-509474
    source: str                  # lipas | loi | osm
    source_id: str
    kind: str                    # kind from types.yaml
    name: Localized
    point: Optional[Coord] = None            # markers
    lines: list[Line] = field(default_factory=list)  # routes (simplified)
    description: Localized = field(default_factory=Localized)
    services: list[str] = field(default_factory=list)   # service keys, e.g. toilet
    marking: Localized = field(default_factory=Localized)  # trail marking in the terrain
    accessibility: Localized = field(default_factory=Localized)
    length_km: Optional[float] = None
    www: str = ""
    admin: str = ""
    status: str = "active"
    city_code: Optional[int] = None
    updated: str = ""
    group_uid: str = ""        # shared id of a multi-part route (used to group GPX output)
    # Clusters of features along the route as named waypoints: [(vertex index, [Feature, ...])]
    # (first Feature = cluster representative whose name is shown)
    waypoints: list = field(default_factory=list)
    # Filled in during enrichment
    areas: list[str] = field(default_factory=list)    # area keys, e.g. kansallispuistot/nuuksio
    region: Optional[str] = None                      # region key, e.g. maakunnat/uusimaa

    @property
    def is_route(self) -> bool:
        return bool(self.lines)

    def all_coords(self) -> list[Coord]:
        if self.point:
            return [self.point]
        return [c for l in self.lines for c in l]


@dataclass
class AreaDef:
    """National park, wilderness area or region."""

    slug: str            # e.g. nuuksio, uusimaa
    category: str        # kansallispuistot | eramaat | maakunnat ...
    name: Localized
    tag: str             # hashtag without #
    geometry: dict
    buffer_m: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.category}/{self.slug}"

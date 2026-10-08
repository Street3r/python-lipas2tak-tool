"""Areas (national parks, wilderness areas, regions) and assigning features to them."""
from __future__ import annotations

import logging
import re
import unicodedata

from . import geo
from .config import Settings, file_slug, slugify
from .model import AreaDef, Feature, Localized

log = logging.getLogger(__name__)


def short_name(full: str, strip: re.Pattern, names: dict[str, str]) -> str:
    """'Nuuksion kansallispuisto' -> 'Nuuksio' (name table or fallback rule)."""
    full = unicodedata.normalize("NFC", full)
    stem = strip.sub("", full).strip()
    if not stem or stem == full:
        return full
    names = {unicodedata.normalize("NFC", k): v for k, v in names.items()}
    if stem in names:
        return names[stem]
    log.warning("Base form of area '%s' missing from config/area_names.yaml; guessing", full)
    return stem[:-1] if stem.endswith("n") else stem


def areas_from_lipas_sites(sites: list[dict], category: str, cfg: dict,
                           names: dict[str, str] | None = None) -> list[AreaDef]:
    strip = re.compile(cfg.get("strip_from_name") or r"(?!x)x")
    names = names or {}
    out = []
    for s in sites:
        feats = ((s.get("location") or {}).get("geometries") or {}).get("features") or []
        polys = []
        for f in feats:
            g = f.get("geometry") or {}
            if g.get("type") == "Polygon":
                polys.append(g["coordinates"])
            elif g.get("type") == "MultiPolygon":
                polys.extend(g["coordinates"])
        if not polys:
            continue
        full = s.get("name") or str(s["lipas-id"])
        short = short_name(full, strip, names)
        en = (s.get("name-localized") or {}).get("en") or full
        out.append(AreaDef(
            slug=file_slug(short),
            category=category,
            name=Localized(fi=full, en=en),
            tag=slugify(short),
            geometry={"type": "MultiPolygon", "coordinates": polys},
            buffer_m=float(cfg.get("buffer_m", 0)),
        ))
    return out


def assign_areas(features: list[Feature], areas: list[AreaDef], route_min_share: float = 0.3,
                 route_min_inside_m: float = 3000.0) -> None:
    """Assign features to special areas (parks etc.) with a buffer.

    A route (part) is included if at least `route_min_share` of its length, or
    at least `route_min_inside_m` metres, lies inside the area. This keeps long
    cycling etc. routes that merely touch the area out of its package.
    """
    for a in areas:
        shape = geo.Area(a.geometry)
        n = 0
        for f in features:
            if f.point is not None:
                hit = shape.within(f.point, a.buffer_m)
            else:
                hit = False
                for l in f.lines:
                    if not shape.touches_line(l, a.buffer_m):
                        continue
                    ins, tot = shape.length_within_m(l, a.buffer_m)
                    if tot == 0 or ins / tot >= route_min_share or ins >= route_min_inside_m:
                        hit = True
                        break
            if hit:
                f.areas.append(a.key)
                n += 1
        log.info("%s %s: %d features", a.category, a.name.fi, n)


def assign_regions(features: list[Feature], regions: list[AreaDef], fallback_km: float = 20.0) -> None:
    """Assign every feature to one region (maakunta).

    For Lipas point features the region is resolved once per municipality
    (a municipality always belongs to one region). Coastal and island features
    may fall outside the generalised boundaries, so the nearest region within
    `fallback_km` is used for them.
    """
    shapes = [(r, geo.Area(r.geometry)) for r in regions]
    by_city: dict[int, str | None] = {}

    def locate(pt: geo.Coord) -> str | None:
        for r, s in shapes:
            if s.contains(pt):
                return r.key
        best, best_d = None, fallback_km * 1000
        for r, s in shapes:
            if not s.within(pt, fallback_km * 1000):
                continue
            d = s.distance_m(pt, fallback_km * 1000)
            if d < best_d:
                best, best_d = r.key, d
        return best

    for f in features:
        if f.point is not None and f.city_code is not None and f.city_code in by_city:
            f.region = by_city[f.city_code]
            continue
        if f.point is not None:
            f.region = locate(f.point)
        else:
            # Route: majority of sample points (the midpoint may be across the
            # border, e.g. cycling routes running on the Norwegian/Swedish side)
            coords = f.all_coords()
            step = max(1, len(coords) // 15)
            votes: dict[str, int] = {}
            for c in coords[::step]:
                k = locate(c)
                if k:
                    votes[k] = votes.get(k, 0) + 1
            f.region = max(votes, key=votes.get) if votes else None
        if f.point is not None and f.city_code is not None and f.region:
            by_city[f.city_code] = f.region
    missing = sum(1 for f in features if not f.region)
    if missing:
        log.warning("%d features without a region", missing)

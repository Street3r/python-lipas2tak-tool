"""Areas (national parks, wilderness areas, regions) and assigning features to them."""
from __future__ import annotations

import logging
import copy
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
    skip = set(cfg.get("exclude_lipas_ids") or [])
    out = []
    for s in sites:
        if s.get("lipas-id") in skip:
            continue
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
        en = ((s.get("name-localized") or {}).get("en")
              or (cfg["name_en"].format(name=short) if cfg.get("name_en") else full))
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


def split_routes_by_region(features: list[Feature], regions: list[AreaDef],
                           min_piece_km: float = 5.0) -> list[Feature]:
    """Split long routes at region borders, so each region gets its own section.

    Without this a long route (e.g. EuroVelo across all of Finland) would be
    put whole into the single region where most of it lies. Runs shorter than
    `min_piece_km` are merged into the neighbouring run. Routes that stay in
    one region are returned unchanged.
    """
    shapes = [(r.key, geo.Area(r.geometry)) for r in regions]

    def locate(c: geo.Coord) -> str | None:
        for key, a in shapes:
            if a.contains(c):
                return key
        return None

    out: list[Feature] = []
    for f in features:
        if not f.is_route or len(f.lines) != 1:
            out.append(f)
            continue
        line = f.lines[0]
        step = max(1, len(line) // 20)
        if len({locate(c) for c in line[::step] + [line[-1]]} - {None}) <= 1:
            out.append(f)
            continue
        # Region of every vertex (outside all regions = same as the previous one)
        keys: list[str | None] = []
        prev = None
        for c in line:
            k = locate(c) or prev
            keys.append(k)
            prev = k
        # Runs of the same region: [start index, end index, key]
        runs: list[list] = []
        for i, k in enumerate(keys):
            if runs and runs[-1][2] == k:
                runs[-1][1] = i
            else:
                runs.append([i, i, k])
        def run_km(r) -> float:
            return line_len(line[max(0, r[0] - 1):r[1] + 1]) / 1000
        # Merge short runs into the previous (or next) run
        merged: list[list] = []
        for r in runs:
            if merged and (run_km(r) < min_piece_km or merged[-1][2] == r[2]):
                merged[-1][1] = r[1]
            else:
                merged.append(r)
        if len(merged) > 1 and run_km(merged[0]) < min_piece_km:
            merged[1][0] = merged[0][0]
            merged.pop(0)
        if len(merged) <= 1:
            out.append(f)
            continue
        for n, (a, b, key) in enumerate(merged, 1):
            g = copy.copy(f)
            g.uid = f"{f.uid}-m{n}"
            g.lines = [line[max(0, a - 1) if n > 1 else a:b + 1]]
            g.length_km = round(line_len(g.lines[0]) / 1000, 1)
            g.group_uid = f.group_uid or f.uid
            g.waypoints = []
            out.append(g)
    return out


def line_len(line: geo.Line) -> float:
    return geo.line_length_m(line) if len(line) >= 2 else 0.0


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

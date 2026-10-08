"""Convert source data to the internal model (Feature) and resolve the feature kind."""
from __future__ import annotations

import copy
import logging
import re
from typing import Iterable, Optional

from . import geo
from .config import Kind, Settings
from .model import Feature, Localized

log = logging.getLogger(__name__)


# --- Classification ---------------------------------------------------------

class Classifier:
    def __init__(self, settings: Settings):
        self.kinds = settings.enabled_kinds()
        self.exclude = re.compile(settings.get("exclude_name_regex") or r"(?!x)x")

    def lipas_type_codes(self) -> list[int]:
        codes: set[int] = set()
        for k in self.kinds:
            codes.update((k.sources.get("lipas") or {}).get("type_codes", []))
        return sorted(codes)

    def loi_types(self) -> list[str]:
        types: set[str] = set()
        for k in self.kinds:
            types.update((k.sources.get("loi") or {}).get("types", []))
        return sorted(types)

    def osm_queries(self) -> list[tuple[str, dict]]:
        """[(kind, tags)] – `tags` may be a single dict or a list of alternative dicts."""
        out = []
        for k in self.kinds:
            src = k.sources.get("osm")
            if not src:
                continue
            tags = src["tags"]
            for t in (tags if isinstance(tags, list) else [tags]):
                out.append((k.key, t))
        return out

    def osm_source(self, kind: str) -> dict:
        for k in self.kinds:
            if k.key == kind:
                return k.sources.get("osm") or {}
        return {}

    def group_of(self, kind: str) -> str:
        for k in self.kinds:
            if k.key == kind:
                return k.group
        return ""

    def excluded(self, name: str) -> bool:
        return bool(name and self.exclude.search(name))

    def for_lipas(self, type_code: int, name: str) -> Optional[Kind]:
        for k in self.kinds:
            src = k.sources.get("lipas")
            if not src or type_code not in src.get("type_codes", []):
                continue
            rx = k.name_regex
            if rx is None or rx.search(name or ""):
                return k
        return None

    def for_loi(self, loi_type: str) -> Optional[Kind]:
        for k in self.kinds:
            if loi_type in (k.sources.get("loi") or {}).get("types", []):
                return k
        return None


# --- Lipas sports-sites -----------------------------------------------------

def _services_from_props(props: dict) -> list[str]:
    s = []
    if props.get("toilet?"):
        s.append("toilet")
    if props.get("parking-place?"):
        s.append("parking")
    if props.get("water-point"):
        s.append("water")
    if props.get("rest-places-count"):
        s.append("rest_places")
    return s


def _lines_from_features(features: list[dict], fids: Optional[set] = None) -> list[geo.Line]:
    lines: list[geo.Line] = []
    for f in features:
        fid = f.get("id") or (f.get("properties") or {}).get("id")
        if fids and fid not in fids:
            continue
        g = f.get("geometry") or {}
        if g.get("type") == "LineString":
            lines.append(geo.drop_z(g["coordinates"]))
        elif g.get("type") == "MultiLineString":
            lines.extend(geo.drop_z(c) for c in g["coordinates"])
    return lines


def _activity_routes(site: dict) -> list[dict]:
    routes = []
    for act in (site.get("activities") or {}).values():
        if isinstance(act, dict):
            routes.extend(r for r in act.get("routes") or [] if isinstance(r, dict))
    return routes


def _prepare_lines(lines: list[geo.Line], settings: Settings) -> list[geo.Line]:
    merged = geo.merge_lines(lines, settings.get("routes", "merge_snap_m", default=5.0))
    tol = settings.get("routes", "simplify_tolerance_m", default=5.0)
    return [geo.simplify(l, tol) for l in merged if len(l) >= 2]


def lipas_site_to_features(site: dict, clf: Classifier, settings: Settings) -> list[Feature]:
    name = site.get("name") or ""
    if clf.excluded(name):
        return []
    type_code = (site.get("type") or {}).get("type-code")
    kind = clf.for_lipas(type_code, name)
    if kind is None:
        return []
    loc = site.get("location") or {}
    features = ((loc.get("geometries") or {}).get("features")) or []
    props = site.get("properties") or {}
    name_loc = site.get("name-localized") or {}
    base = dict(
        source="lipas",
        source_id=str(site["lipas-id"]),
        kind=kind.key,
        description=Localized(fi=site.get("comment") or ""),
        services=_services_from_props(props),
        www=site.get("www") or "",
        admin=site.get("admin") or "",
        status=site.get("status") or "active",
        city_code=(loc.get("city") or {}).get("city-code"),
        updated=site.get("event-date") or "",
    )
    lid = site["lipas-id"]

    if not kind.is_route:
        pts = [f["geometry"]["coordinates"] for f in features
               if (f.get("geometry") or {}).get("type") == "Point"]
        if not pts:
            log.debug("Lipas %s: no point geometry", lid)
            return []
        return [Feature(uid=f"lipas-{lid}", name=Localized(fi=name, en=name_loc.get("en") or ""),
                        point=(float(pts[0][0]), float(pts[0][1])), **base)]

    # Routes: if `activities` contains sub-routes (Luontoon.fi enrichment),
    # each becomes its own route; otherwise the whole site is one route.
    out: list[Feature] = []
    sub = _activity_routes(site)
    if sub:
        for i, r in enumerate(sub, 1):
            fids = set(r.get("fids") or [])
            lines = _prepare_lines(_lines_from_features(features, fids or None), settings)
            if not lines:
                continue
            rname = Localized.from_any(r.get("route-name"))
            if not rname.fi:
                rname = Localized(fi=name, en=name_loc.get("en") or "")
            desc = Localized.from_any(r.get("description-short") or r.get("description-long"))
            if not desc.fi:
                desc = base["description"]
            length = r.get("route-length-km") or (props.get("route-length-km") if len(sub) == 1 else None)
            f = Feature(
                uid=f"lipas-{lid}" if len(sub) == 1 else f"lipas-{lid}-r{i}",
                name=rname, lines=lines,
                marking=Localized.from_any(r.get("route-marking")),
                accessibility=Localized.from_any(r.get("accessibility-classification")),
                length_km=length,
                **{**base, "description": desc},
            )
            out.append(f)
    if not out:
        lines = _prepare_lines(_lines_from_features(features), settings)
        if not lines:
            return []
        out.append(Feature(uid=f"lipas-{lid}", name=Localized(fi=name, en=name_loc.get("en") or ""),
                           lines=lines, length_km=props.get("route-length-km"), **base))
    # Disconnected parts become features of their own so that area and region
    # assignment is done per part (long routes may cross several areas).
    # GPX output groups the parts back together.
    split: list[Feature] = []
    for f in out:
        if len(f.lines) == 1:
            if f.length_km is None:
                f.length_km = round(geo.line_length_m(f.lines[0]) / 1000, 1)
            split.append(f)
            continue
        for i, line in enumerate(f.lines, 1):
            g = copy.copy(f)
            g.uid = f"{f.uid}-{i}"
            g.lines = [line]
            g.length_km = round(geo.line_length_m(line) / 1000, 1)
            g.group_uid = f.uid
            split.append(g)
    return split


# --- Lipas LOIs ---------------------------------------------------------------

def loi_to_feature(loi: dict, clf: Classifier) -> Optional[Feature]:
    kind = clf.for_loi(loi.get("loi-type") or "")
    if kind is None:
        return None
    name = Localized.from_any(loi.get("name"))
    if clf.excluded(name.fi):
        return None
    feats = ((loi.get("geometries") or {}).get("features")) or []
    if not feats or not feats[0].get("geometry"):
        return None
    pt = geo.representative_point(feats[0]["geometry"])
    return Feature(
        uid=f"loi-{loi['id']}",
        source="loi",
        source_id=str(loi["id"]),
        kind=kind.key,
        name=name,
        point=pt,
        description=Localized.from_any(loi.get("description")),
        accessibility=Localized.from_any(loi.get("accessibility")),
        status=loi.get("status") or "active",
        updated=loi.get("event-date") or "",
    )


# --- OSM ------------------------------------------------------------------------

def osm_to_feature(el: dict, kind_key: str) -> Optional[Feature]:
    if "lat" in el:
        pt = (float(el["lon"]), float(el["lat"]))
    elif "center" in el:
        pt = (float(el["center"]["lon"]), float(el["center"]["lat"]))
    else:
        return None
    tags = el.get("tags") or {}
    services = []
    if tags.get("wheelchair") == "yes":
        services.append("wheelchair")
    return Feature(
        uid=f"osm-{el['type'][0]}{el['id']}",
        source="osm",
        source_id=f"{el['type']}/{el['id']}",
        kind=kind_key,
        name=Localized(fi=tags.get("name") or tags.get("name:fi") or "", en=tags.get("name:en") or ""),
        point=pt,
        description=Localized(fi=tags.get("description") or ""),
        services=services,
        www=tags.get("website") or "",
    )


# When one OSM element matches several kinds (e.g. a lean-to also tagged as a fire
# pit), the kind earlier in this list wins; kinds not listed lose to listed ones.
OSM_MERGE_PRIORITY = ["tupa", "kota", "laavu", "keittokatos", "nakotorni", "telttapaikka",
                      "nuotiopaikka", "nakoalapaikka", "kaymala", "vesipiste"]
# The losing kind is added to the winner's services ...
OSM_MERGE_SERVICE = {"nuotiopaikka": "fireplace", "nakoalapaikka": "viewpoint",
                     "kaymala": "toilet", "vesipiste": "water"}
# ... unless the winner already implies it
OSM_MERGE_IMPLIED = {("keittokatos", "nuotiopaikka"), ("nakotorni", "nakoalapaikka")}


def merge_osm_kinds(candidates: dict[str, list[Feature]],
                    priority: list[str] = OSM_MERGE_PRIORITY) -> dict[str, list[Feature]]:
    """Resolve OSM elements that matched several kinds: one feature per element.

    candidates: {kind: [Feature]} -> {kind: [Feature]} with each UID only once.
    """
    rank = {k: i for i, k in enumerate(priority)}
    by_uid: dict[str, list[Feature]] = {}
    for kind, feats in candidates.items():
        for f in feats:
            by_uid.setdefault(f.uid, []).append(f)
    out: dict[str, list[Feature]] = {k: [] for k in candidates}
    for uid, fs in by_uid.items():
        fs.sort(key=lambda f: rank.get(f.kind, len(rank)))
        win = fs[0]
        for lose in fs[1:]:
            svc = OSM_MERGE_SERVICE.get(lose.kind)
            if svc and (win.kind, lose.kind) not in OSM_MERGE_IMPLIED and svc not in win.services:
                win.services.append(svc)
        out[win.kind].append(win)
    return out


def dedupe_osm(features: Iterable[Feature], context: list[Feature], *, context_radius_m: float,
               dedupe_radius_m: float, group_of=None) -> list[Feature]:
    """Keep OSM features that are near outdoor features and are not duplicates.

    Duplicate = a feature of the same group (e.g. shelters: lean-to/kota/hut)
    within `dedupe_radius_m`. Lipas/LOI always wins over OSM. Already accepted
    OSM features are compared too (node + way of the same object).
    """
    group_of = group_of or (lambda k: k)
    grid = geo.GridIndex.for_radius(max(context_radius_m, dedupe_radius_m))
    for f in context:
        for c in f.all_coords():
            grid.add(c, group_of(f.kind))
    out = []
    for f in features:
        p = f.point
        assert p is not None
        g = group_of(f.kind)
        near_ctx = False
        dup = False
        for c, cg in grid.near(p):
            d = geo.haversine(p, c)
            if d <= dedupe_radius_m and cg == g:
                dup = True
                break
            if d <= context_radius_m:
                near_ctx = True
        if near_ctx and not dup:
            out.append(f)
            grid.add(p, g)
    return out

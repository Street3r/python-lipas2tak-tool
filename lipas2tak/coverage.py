"""Area coverage report: raw items inside an area that are not in its package, and why.

Reads saved raw data (`lipas2tak fetch --dump` / the generator's /data/raw),
runs the same normalisation as a build and, for every area of the given
categories, lists the Lipas sites, LOIs and OSM elements located inside the
area (with its buffer) that did not end up in the area's data package.

Run: python -m lipas2tak.coverage /data/raw [category or area ...]
     e.g. kansallispuistot, or kansallispuistot/petkeljarvi
     (default categories: eramaat valtion_retkeilyalueet)
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from lipas2tak import geo, normalize, pipeline
from lipas2tak.config import load_settings

DEFAULT_CATEGORIES = ["eramaat", "valtion_retkeilyalueet"]


def _coords(geom: dict) -> list:
    """All (lon, lat) pairs of a GeoJSON geometry, feature or feature collection."""
    if not geom:
        return []
    t = geom.get("type")
    if t == "FeatureCollection":
        return [c for f in geom.get("features") or [] for c in _coords(f)]
    if t == "Feature":
        return _coords(geom.get("geometry") or {})
    out = []

    def walk(x):
        if x and isinstance(x[0], (int, float)):
            out.append((float(x[0]), float(x[1])))
        else:
            for y in x:
                walk(y)
    walk(geom.get("coordinates") or [])
    return out


def _osm_point(el: dict):
    if "lat" in el:
        return float(el["lon"]), float(el["lat"])
    if "center" in el:
        return float(el["center"]["lon"]), float(el["center"]["lat"])
    return None


def raw_items(raw: pipeline.RawData):
    """(source, source_id, name, type, coords) for every raw item."""
    for s in raw.sites:
        yield ("lipas", str(s["lipas-id"]), s.get("name") or "", f"type {(s.get('type') or {}).get('type-code')}",
               _coords((s.get("location") or {}).get("geometries") or {}))
    for l in raw.lois:
        yield ("loi", str(l["id"]), ((l.get("name") or {}).get("fi") or ""), l.get("loi-type") or "",
               _coords(l.get("geometries") or {}))
    seen = set()
    for kind, els in raw.osm.items():
        for e in els:
            key = f"{e['type']}/{e['id']}"
            if key in seen:
                continue
            seen.add(key)
            pt = _osm_point(e)
            tags = e.get("tags") or {}
            yield ("osm", key, tags.get("name") or "", f"osm {kind}", [pt] if pt else [])


def _nearest_same_group(pt, kind: str, feats: list, clf, radius_m: float = 300.0) -> str:
    """The nearest kept feature of the same group as `kind`: 'name (source, distance m)'."""
    group = clf.group_of(kind)
    best = None
    for f in feats:
        if f.point is None or clf.group_of(f.kind) != group:
            continue
        d = geo.haversine(pt, f.point)
        if d <= radius_m and (best is None or d < best[0]):
            best = (d, f)
    if best is None:
        return ""
    d, f = best
    return f"{f.name.fi or '(no name)'} ({f.source}, {d:.0f} m)"


def report(raw_dir: Path, categories: list[str]) -> str:
    settings = load_settings()
    raw = pipeline.RawData.load(raw_dir)
    clf = normalize.Classifier(settings)
    feats, areas = pipeline.build_features(settings, raw, clf)
    by_source: dict[tuple[str, str], list] = {}
    for f in feats:
        by_source.setdefault((f.source, f.source_id), []).append(f)
    items = list(raw_items(raw))

    lines = []
    totals: Counter = Counter()
    for area in sorted((a for a in areas.values() if a.category in categories or a.key in categories),
                       key=lambda a: a.key):
        shape = geo.Area(area.geometry)
        missing = []
        included = 0
        for source, sid, name, typ, coords in items:
            if not coords or not any(shape.within(c, area.buffer_m) for c in coords[:: max(1, len(coords) // 50)]):
                continue
            fs = by_source.get((source, sid), [])
            if any(area.key in f.areas and settings.kinds[f.kind].area_packages for f in fs):
                included += 1
                continue
            if not fs:
                if source == "osm":
                    reason = "OSM: duplicate of a nearby Lipas/OSM feature of the same group"
                    match = _nearest_same_group(coords[0], typ.removeprefix("osm "), feats, clf)
                    if match:
                        name = f"{name or '(no name)'} = {match}"
                elif clf.excluded(name):
                    reason = "excluded by name (test data)"
                else:
                    reason = "not classified (type not in types.yaml or no geometry)"
            elif all(not settings.kinds[f.kind].area_packages for f in fs):
                reason = f"kind {fs[0].kind}: area_packages false (only in the route layers)"
            else:
                reason = "route: too little of it inside the area (routes.area_min_share / area_min_inside_m)"
            missing.append((reason, typ, name or "(no name)", f"{source}:{sid}"))
            totals[reason] += 1
        lines.append(f"\n## {area.key} ({area.name.fi}): {included} included, {len(missing)} not included")
        for reason, typ, name, ref in sorted(missing):
            lines.append(f"- {reason} | {typ} | {name} | {ref}")
    head = ["# Area coverage", "", "Not included, by reason:"]
    head += [f"- {n} × {r}" for r, n in totals.most_common()] or ["- nothing"]
    return "\n".join(head + lines) + "\n"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    print(report(Path(argv[0]), argv[1:] or DEFAULT_CATEGORIES))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

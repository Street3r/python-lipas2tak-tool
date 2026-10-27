"""Full run: fetch -> normalise -> enrich -> write outputs -> index.json."""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import areas as areas_mod
from . import attribution, geo, normalize, remarks, waypoints
from .config import Settings, file_slug
from .model import AreaDef, Feature, Localized
from .sources import lipas, osm, regions
from .sources.http import CachedClient
from .writers import cot, datapackage, gpx, iconset, kml, remote_resource, share

log = logging.getLogger(__name__)


# --- Raw data ---------------------------------------------------------------

@dataclass
class RawData:
    sites: list[dict] = field(default_factory=list)              # Lipas sports-sites
    lois: list[dict] = field(default_factory=list)               # Lipas LOIs
    osm: dict[str, list[dict]] = field(default_factory=dict)     # kind -> OSM elements
    area_sites: dict[str, list[dict]] = field(default_factory=dict)  # category -> Lipas area sites
    regions: list[dict] = field(default_factory=list)            # GeoJSON features
    warnings: list[str] = field(default_factory=list)            # source problems of the fetch

    FILES = ("sites", "lois", "osm", "area_sites", "regions", "warnings")

    def dump(self, d: Path) -> None:
        d.mkdir(parents=True, exist_ok=True)
        for name in self.FILES:
            (d / f"{name}.json").write_text(json.dumps(getattr(self, name), ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, d: Path) -> "RawData":
        kw = {}
        for name in cls.FILES:
            p = d / f"{name}.json"
            if p.exists():
                kw[name] = json.loads(p.read_text(encoding="utf-8"))
        return cls(**kw)


def fetch_raw(settings: Settings, clf: normalize.Classifier) -> RawData:
    lp = settings.get("sources", "lipas")
    client = CachedClient(settings.path("cache") / "http", max_age_h=lp.get("cache_max_age_h", 20),
                          delay_s=lp.get("request_delay_s", 0.3))
    api = lipas.LipasClient(client, lp["base_url"], lp.get("page_size", 100))
    raw = RawData()
    raw.sites = list(api.sports_sites(clf.lipas_type_codes(), lp.get("statuses")))
    for cat, acfg in (settings.get("areas") or {}).items():
        if acfg.get("enabled") and acfg.get("lipas_type_codes"):
            raw.area_sites[cat] = list(api.sports_sites(acfg["lipas_type_codes"], lp.get("statuses")))
    lc = settings.get("sources", "lois") or {}
    if lc.get("enabled", True) and clf.loi_types():
        raw.lois = list(api.lois(clf.loi_types(), lc.get("statuses")))
    oc = settings.get("sources", "osm") or {}
    if oc.get("enabled"):
        bboxes = area_bboxes(settings, raw)
        # Time budget of all OSM queries: when the Overpass servers are stuck, the
        # remaining queries use their cached results instead of hours of retries
        budget_min = float(oc.get("max_total_min", 120))
        deadline = time.time() + budget_min * 60
        for kind, tags in clf.osm_queries():
            only_in_areas = clf.osm_source(kind).get("only_in_areas")
            if only_in_areas and not bboxes:
                continue
            what = f"OSM {kind} {_tags_text(tags)}"
            n_stale = len(client.stale)
            try:
                urls = [oc["overpass_url"], *(oc.get("overpass_fallback_urls") or [])]
                els = osm.fetch(client, urls, tags, bboxes if only_in_areas else None, deadline=deadline)
            except Exception as e:  # OSM is a supplementary source: errors do not abort the run
                log.error("OSM query failed (%s %s): %s", kind, tags, e)
                raw.warnings.append(f"{what}: query failed and no cached result, left out of this build")
                continue
            if len(client.stale) > n_stale:
                raw.warnings.append(f"{what}: Overpass failed, used the cached result from "
                                    f"{_age_text(client.stale[-1][1])}")
            seen = {(e["type"], e["id"]) for e in raw.osm.get(kind, [])}
            raw.osm.setdefault(kind, []).extend(e for e in els if (e["type"], e["id"]) not in seen)
        if time.time() >= deadline:
            raw.warnings.append(f"OSM: time budget of {budget_min:g} min used up; "
                                "the remaining queries used cached results")
    if (settings.get("areas", "maakunnat") or {}).get("enabled"):
        rc = settings.get("sources", "regions")
        n_stale = len(client.stale)
        # Boundaries rarely change: if the service fails or returns nothing, the
        # previous result is used rather than dropping every region package
        data = client.get_json(rc["wfs_url"], params={
            "service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeName": rc["layer"],
            "outputFormat": "application/json", "srsName": "EPSG:4326"},
            stale_ok=True, validate=_has_features)
        if len(client.stale) > n_stale:
            raw.warnings.append(f"Region boundaries: Statistics Finland WFS failed, used the cached result "
                                f"from {_age_text(client.stale[-1][1])}")
        raw.regions = data.get("features", [])
    return raw


def _has_features(data) -> None:
    if not (data or {}).get("features"):
        raise ValueError("no features in the response")


def _tags_text(tags: dict) -> str:
    return ",".join(f"{k}={v}" for k, v in tags.items())


def _age_text(hours: float) -> str:
    return f"{hours / 24:.0f} days ago" if hours >= 48 else f"{hours:.0f} h ago"


def area_bboxes(settings: Settings, raw: RawData) -> list[tuple[float, float, float, float]]:
    """Bounding boxes (south, west, north, east) of the protected areas, with their buffer."""
    out = []
    for cat, sites in raw.area_sites.items():
        for a in areas_mod.areas_from_lipas_sites(sites, cat, settings.get("areas", cat),
                                                  settings.area_names.get(cat)):
            pts = [c for poly in a.geometry["coordinates"] for ring in poly for c in ring]
            lat = [p[1] for p in pts]
            dlat = a.buffer_m / 111_000
            dlon = dlat / max(0.1, math.cos(math.radians(max(lat))))
            out.append((min(lat) - dlat, min(p[0] for p in pts) - dlon,
                        max(lat) + dlat, max(p[0] for p in pts) + dlon))
    return sorted(out)


# --- Enrichment ---------------------------------------------------------------

def build_features(settings: Settings, raw: RawData, clf: normalize.Classifier
                   ) -> tuple[list[Feature], dict[str, AreaDef]]:
    feats: list[Feature] = []
    log.info("Processing %d Lipas sites and %d LOIs", len(raw.sites), len(raw.lois))
    for n, s in enumerate(raw.sites, 1):
        feats.extend(normalize.lipas_site_to_features(s, clf, settings))
        if n % 2000 == 0:
            log.info("  %d/%d", n, len(raw.sites))
    for l in raw.lois:
        f = normalize.loi_to_feature(l, clf)
        if f:
            feats.append(f)
    # Same UID twice (e.g. overlapping pages) -> last one wins
    feats = list({f.uid: f for f in feats}.values())

    oc = settings.get("sources", "osm") or {}
    enabled = {k.key for k in settings.enabled_kinds()}
    # Protected areas are known before OSM filtering: OSM features inside them
    # count as being in an outdoor context even when Lipas has nothing nearby
    area_defs = {cat: areas_mod.areas_from_lipas_sites(sites, cat, settings.get("areas", cat),
                                                       settings.area_names.get(cat))
                 for cat, sites in raw.area_sites.items()}
    shapes = [(geo.Area(a.geometry), a.buffer_m) for defs in area_defs.values() for a in defs]

    def in_area(pt) -> bool:
        return any(shape.within(pt, buf) for shape, buf in shapes)

    candidates = {}
    for kind, els in raw.osm.items():
        if kind not in enabled:
            continue
        cand = [f for f in (normalize.osm_to_feature(e, kind) for e in els) if f]
        candidates[kind] = [f for f in cand if not clf.excluded(f.name.fi)]
    # An OSM element can match several kinds (e.g. a lean-to also tagged as a fire pit):
    # keep one feature under the main kind and add the other as a service
    candidates = normalize.merge_osm_kinds(candidates)
    for kind, cand in candidates.items():
        src = clf.osm_source(kind)
        kept = normalize.dedupe_osm(
            cand, feats,
            # only_in_areas: e.g. parking, which is everywhere near routes in towns
            context_radius_m=0 if src.get("only_in_areas") else
            src.get("context_radius_m", oc.get("context_radius_m", 300)),
            dedupe_radius_m=src.get("dedupe_radius_m", oc.get("dedupe_radius_m", 40)),
            group_of=clf.group_of, in_area=in_area)
        log.info("OSM %s: %d/%d included", kind, len(kept), len(cand))
        feats.extend(kept)

    log.info("Features after normalisation: %d", len(feats))
    regs = regions.fetch_regions_from_features(raw.regions) if raw.regions else []
    if regs:
        before = len(feats)
        feats = areas_mod.split_routes_by_region(feats, regs)
        log.info("Long routes split at region borders: %d new sections", len(feats) - before)
    wp = settings.get("routes", "waypoints") or {}
    if wp.get("enabled", True):
        waypoints.attach_waypoints(
            feats, {k.key: k.group for k in settings.kinds.values()},
            groups=wp.get("groups", ["suojat", "tulentekopaikat", "telttailu", "nakotornit"]),
            radius_m=wp.get("radius_m", 75), cluster_m=wp.get("cluster_m", 200))
    all_areas: dict[str, AreaDef] = {}
    for cat, defs in area_defs.items():
        areas_mod.assign_areas(feats, defs,
                               route_min_share=settings.get("routes", "area_min_share", default=0.3),
                               route_min_inside_m=settings.get("routes", "area_min_inside_m", default=3000))
        all_areas.update({a.key: a for a in defs})
    if regs:
        areas_mod.assign_regions(feats, regs)
        all_areas.update({r.key: r for r in regs})
    return feats, all_areas


# --- Outputs --------------------------------------------------------------------

def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


ENDPOINTS = {"start": {"fi": "alku", "en": "start"}, "end": {"fi": "loppu", "en": "end"},
             "loop": {"fi": "lähtö ja paluu", "en": "start and finish"}}

def _route_parts(f: Feature) -> list[tuple[str, list]]:
    if len(f.lines) == 1:
        return [(f.uid, f.lines[0])]
    return [(f"{f.uid}-{i}", l) for i, l in enumerate(f.lines, 1)]


def _whole(f: Feature) -> Feature:
    """The feature as a whole network (name without the section length)."""
    g = copy.copy(f)
    g.length_km = g.network_km
    g.network_km = None
    return g


def _since(times: dict, key: str, digest: str, now: datetime) -> datetime:
    """CoT time of an item: when its content last changed (kept in state.json).

    Unchanged items keep their timestamp, so unchanged files stay byte-identical
    between runs, and a changed item always gets a newer time.
    """
    prev = times.get(key)
    if prev and prev[0] == digest:
        return datetime.fromisoformat(prev[1])
    times[key] = [digest, now.isoformat()]
    return now


def write_area(settings: Settings, area: AreaDef, feats: list[Feature], all_areas: dict[str, AreaDef],
               out_root: Path, now: datetime, times: Optional[dict] = None,
               outputs: Optional[dict] = None) -> list[dict]:
    """Write all outputs of one area in every language. Returns index entries.

    `times`: {"<area>/<lang>:<uid>": [digest, iso time]}, updated in place.
    `outputs`: overrides of the `outputs` settings for this area.
    """
    times = {} if times is None else times
    kinds = settings.kinds
    icons_dir = settings.icon_dirs()
    outs = {**(settings.get("outputs") or {}), **(outputs or {})}
    stroke = float(settings.get("routes", "stroke_weight", default=4.0))
    route_format = settings.get("routes", "cot_format", default="route")
    snap_m = float(settings.get("routes", "merge_snap_m", default=5.0))
    base_url = (settings.get("public_base_url") or "").rstrip("/")
    entries = []
    feats = sorted(feats, key=lambda f: (kinds[f.kind].group, f.kind, f.name.fi, f.uid))

    for lang in settings.languages:
        rel_dir = Path(lang) / area.category / area.slug
        d = out_root / rel_dir
        stem = f"{area.slug}_{lang}"
        title = area.name.get(lang)
        files: dict[str, str] = {}
        cot_items: list[tuple[str, str, str]] = []
        uid_digests: dict[str, str] = {}
        latest: Optional[datetime] = None   # newest content change in this package
        package_uid = ""
        folders: dict[str, kml.Folder] = {}
        icon_styles: dict[str, str] = {}
        line_styles: dict[str, tuple[str, float]] = {}
        gpx_groups: dict[str, tuple[str, str, str, list]] = {}  # group -> (name, remarks, www, lines)

        for f in feats:
            k = kinds[f.kind]
            name = remarks.display_name(f, k, lang)
            rem = remarks.remarks(f, k, lang, all_areas, settings)
            folder = folders.setdefault(k.group, kml.Folder(settings.groups[k.group]["label"][lang]))
            if f.is_route:
                parts = _route_parts(f)
                for uid, line in parts:
                    digest = _digest(name + rem + repr(line) + repr(f.waypoints and [i for i, _ in f.waypoints]))
                    t = _since(times, f"{area.key}/{lang}:{uid}", digest, now)
                    latest = max(latest, t) if latest else t
                    if route_format == "shape" or f.network_km:
                        # Path network sections are drawn lines: no start/end points per piece
                        xml = cot.polyline(uid, line, name, rem, k.color or "#FF0000", stroke, now=t)
                    else:
                        loop = geo.is_closed(line, snap_m)
                        start = ENDPOINTS["loop" if loop else "start"][lang]
                        end = ENDPOINTS["loop" if loop else "end"][lang]
                        wps = {i: (remarks.display_name(ws[0], kinds[ws[0].kind], lang),
                                   ", ".join(dict.fromkeys(kinds[w.kind].label.get(lang) or kinds[w.kind].label["fi"]
                                                           for w in ws)))
                               for i, ws in f.waypoints}
                        xml = cot.route(uid, line, name, rem, k.color or "#FF0000", waypoints=wps,
                                        start_name=f"{name} – {start}",
                                        end_name=f"{name} – {end}",
                                        stroke_weight=stroke, method=k.route_method,
                                        route_kind=k.route_type, now=t)
                    cot_items.append((uid, name, xml))
                    uid_digests[uid] = digest
                line_styles[f"s-{k.key}"] = (k.color or "#FF0000", stroke)
                folder.placemarks.append(kml.Placemark(f.uid, name, rem, f"s-{k.key}", lines=f.lines))
                gkey = f.group_uid or f.uid
                if gkey not in gpx_groups:
                    whole = _whole(f) if f.network_km else f
                    gpx_groups[gkey] = (remarks.display_name(whole, k, lang),
                                        remarks.remarks(whole, k, lang, all_areas, settings), f.www, [])
                g = gpx_groups[gkey]
                g[3].append((f.lines[0], {i: remarks.display_name(ws[0], kinds[ws[0].kind], lang)
                                          for i, ws in f.waypoints}))
            else:
                assert f.point
                path = iconset.iconsetpath(k.icon) if k.icon else None
                digest = _digest(name + rem + repr(f.point) + (path or ""))
                t = _since(times, f"{area.key}/{lang}:{f.uid}", digest, now)
                latest = max(latest, t) if latest else t
                xml = cot.marker(f.uid, k.cot_type, f.point[1], f.point[0], name, rem, path, now=t)
                cot_items.append((f.uid, name, xml))
                uid_digests[f.uid] = digest
                if k.icon:
                    icon_styles[f"s-{k.key}"] = k.icon
                folder.placemarks.append(kml.Placemark(f.uid, name, rem, f"s-{k.key}", point=f.point))

        if outs.get("datapackage", True) and cot_items:
            p = d / f"{stem}.zip"
            # The version date in the name shows which edition is loaded; the package
            # UID changes with the content (see writers/datapackage.py)
            version = latest.strftime("%Y-%m-%d") if latest else ""
            package_uid = datapackage.write(p, f"{title} ({lang}) {version}".strip(), f"{area.key}/{lang}",
                                            cot_items, remarks=attribution.SHORT,
                                            notice=attribution.notice_text(),
                                            on_receive_delete=bool(outs.get("datapackage_on_receive_delete", False)))
            files["datapackage"] = str(p.relative_to(out_root))
        if outs.get("kmz", True) and cot_items:
            p = d / f"{stem}.kmz"
            kml.write_kmz(p, title, list(folders.values()), icon_styles, line_styles, icons_dir)
            files["kmz"] = str(p.relative_to(out_root))
            if outs.get("network_link", True):
                nl = d / f"{stem}.kml"
                kml.write_network_link(nl, title, f"{base_url}/{files['kmz']}", outs.get("network_link_refresh_s", 86400))
                files["network_link"] = str(nl.relative_to(out_root))
                if outs.get("link_package", True):
                    # Package that adds the refreshing link to ATAK when opened (QR code / button)
                    lp = d / f"{stem}_link.zip"
                    b = geo.Area(area.geometry).bbox
                    remote_resource.write(lp, title, f"{base_url}/{files['network_link']}",
                                          outs.get("network_link_refresh_s", 86400),
                                          point=((b[1] + b[3]) / 2, (b[0] + b[2]) / 2))
                    files["link_package"] = str(lp.relative_to(out_root))
            if outs.get("kmz_per_group", True):
                for group, folder in folders.items():
                    if not folder.placemarks:
                        continue
                    gname = f"{title} – {settings.groups[group]['label'][lang]}"
                    p = d / f"{stem}_{group}.kmz"
                    kml.write_kmz(p, gname, [folder], icon_styles, line_styles, icons_dir)
                    files[f"kmz_{group}"] = str(p.relative_to(out_root))
                    if outs.get("network_link", True) and outs.get("network_link_per_group", False):
                        nl = d / f"{stem}_{group}.kml"
                        kml.write_network_link(nl, gname, f"{base_url}/{files[f'kmz_{group}']}",
                                               outs.get("network_link_refresh_s", 86400))
                        files[f"network_link_{group}"] = str(nl.relative_to(out_root))
        gpx_files = [(f"{file_slug(n) or key}_{key}.gpx", gpx.route_gpx(n, r, lines, w))
                     for key, (n, r, w, lines) in gpx_groups.items()]
        if outs.get("gpx", True) and gpx_files:
            p = d / f"{stem}_gpx.zip"
            gpx.write_zip(p, gpx_files + [("ATTRIBUTION.txt", attribution.notice_text())])
            files["gpx_zip"] = str(p.relative_to(out_root))

        counts: dict[str, int] = {}
        for f in feats:
            counts[f.kind] = counts.get(f.kind, 0) + 1
        entries.append({
            "key": area.key, "category": area.category, "slug": area.slug, "lang": lang,
            "name": title, "tag": area.tag, "files": files, "counts": counts,
            "uids": uid_digests,
            "datapackage_uid": package_uid,
            # Date of the newest content change in this area (stable between runs)
            "updated": latest.date().isoformat() if latest else "",
        })
    return entries


def run(settings: Settings, raw: RawData, only: Optional[list[str]] = None,
        now: Optional[datetime] = None, next_check: Optional[datetime] = None) -> dict:
    """Produce all files. `only`: restrict to area keys or slugs (e.g. kansallispuistot/nuuksio)."""
    now = now or datetime.now(timezone.utc)
    clf = normalize.Classifier(settings)
    feats, all_areas = build_features(settings, raw, clf)
    out_root = settings.path("output")
    staging = out_root.parent / (out_root.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    used_icons = [k.icon for k in settings.enabled_kinds() if k.icon]
    iconset.write(staging / "iconset" / "lipas2tak_iconset.zip", settings.icon_dirs(), used_icons)

    state_path = settings.path("cache") / "state.json"
    prev_state = _load_state(state_path)
    times = prev_state.get("since", {})
    index_areas = []
    warnings: list[str] = list(raw.warnings)
    targets = [a for a in all_areas.values() if not only or a.key in only or a.slug in only]
    for area in sorted(targets, key=lambda a: a.key):
        if area.name_guessed:
            warnings.append(f"{area.key}: base form of '{area.name.fi}' guessed; add it to config/area_names.yaml")
    if (settings.get("areas", "maakunnat") or {}).get("enabled") and \
            not any(a.category == "maakunnat" for a in all_areas.values()):
        warnings.append("maakunnat: no region boundaries, no region packages")
    empty: set[str] = set()
    in_packages = [f for f in feats if settings.kinds[f.kind].area_packages]
    for area in sorted(targets, key=lambda a: (a.category, a.slug)):
        if area.category == "maakunnat":
            sel = [f for f in in_packages if f.region == area.key]
        else:
            sel = [f for f in in_packages if area.key in f.areas]
        if not sel:
            log.info("%s: no features, skipped", area.key)
            warnings.append(f"{area.key}: no features, no package")
            empty.add(area.key)
            continue
        index_areas.extend(write_area(settings, area, sel, all_areas, staging, now, times))
    route_outs = settings.get("route_types", "outputs", default=None) or {}
    for order, (area, sel, parent) in enumerate(route_type_areas(settings, feats)):
        if not only or area.key in only or area.slug in only:
            for e in write_area(settings, area, sel, all_areas, staging, now, times, route_outs):
                e["order"] = order
                if parent:   # sub-layer: shown in a subfolder of its route type
                    e["parent"], e["parent_name"] = parent[0], parent[1].get(e["lang"])
                index_areas.append(e)

    links, link_packages = write_link_collections(settings, index_areas, staging)
    kind_counts: dict[str, int] = {}
    for f in feats:
        kind_counts[f.kind] = kind_counts.get(f.kind, 0) + 1
    if not only:
        warnings.extend(compare_with_previous(settings, prev_state, index_areas, kind_counts, empty))

    index = {
        "generated": now.isoformat(),
        "public_base_url": settings.get("public_base_url"),
        "iconset": "iconset/lipas2tak_iconset.zip",
        "iconset_uid": iconset.ICONSET_UID,
        "license": attribution.LICENSE_ID,
        "license_url": attribution.LICENSE_URL,
        "attribution": attribution.ATTRIBUTION,
        "links": links,
        "link_packages": link_packages,
        "share": {},
        "areas": index_areas,
    }
    if (settings.get("outputs") or {}).get("share_pages", True):
        titles = {c: {lang: _category_title(settings, c, lang) for lang in settings.languages}
                  for c in sorted({e["category"] for e in index_areas}, key=category_sort_key(settings))}
        index["share"] = share.write_share_pages(staging, index, titles, settings.languages)
    max_mb = float(settings.get("quality", "max_file_mb", default=50))
    for p in sorted(staging.rglob("*")):
        if p.is_file() and p.stat().st_size > max_mb * 1e6:
            warnings.append(f"{p.relative_to(staging).as_posix()}: {p.stat().st_size / 1e6:.1f} MB "
                            f"(limit {max_mb:g} MB; GitHub rejects files over 100 MB)")
    for w in warnings:
        log.warning("Quality: %s", w)
    # When the sources were last checked. Kept in its own small file so that the
    # pages stay byte-identical when nothing changed (they read it with JavaScript).
    status = {"checked": now.isoformat(timespec="seconds")}
    if next_check:
        status["next_check"] = next_check.isoformat(timespec="seconds")
    if warnings:   # the Stale data workflow of the data repository opens an issue for these
        status["warnings"] = warnings
    (staging / "status.json").write_text(json.dumps(status), encoding="utf-8")
    index["next_check"] = status.get("next_check", "")
    (staging / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    (staging / "index.html").write_text(render_index_html(index), encoding="utf-8")

    changes = diff_state(state_path, index_areas, now, times, kind_counts if not only else None)
    # Atomic swap: old (removed) files disappear at the same time
    old = out_root.parent / (out_root.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if out_root.exists():
        out_root.rename(old)
    staging.rename(out_root)
    if old.exists():
        shutil.rmtree(old)
    log.info("Done: %d areas, %d features", len({e['key'] for e in index_areas}), len(feats))
    return {"index": index, "changes": changes, "features": len(feats), "warnings": warnings}


def _category_title(settings: Settings, category: str, lang: str) -> str:
    if category == ROUTE_CATEGORY:
        title = settings.get("route_types", "title", default=None) or {}
    else:
        title = settings.get("areas", category, "title", default=None) or {}
    return title.get(lang) or category


ROUTE_CATEGORY = "reitit"


def category_sort_key(settings: Settings):
    """Categories in the order of config.yaml `areas`, route types last."""
    order = [*(settings.get("areas") or {}), ROUTE_CATEGORY]
    return lambda c: (order.index(c) if c in order else len(order), c)


def route_type_areas(settings: Settings, feats: list[Feature]
                     ) -> list[tuple[AreaDef, list[Feature], Optional[tuple[str, Localized]]]]:
    """Nationwide route layers: one pseudo-area per route type (config.yaml route_types).

    Written like an area (category "reitit"), so each type gets its own KMZ,
    network link and link package, and links/reitit_<lang>.kml collects them.
    A type with `subtypes` is split into one layer per subtype; the third item
    is then (type slug, type name), so the links can be put in a subfolder.
    """
    rc = settings.get("route_types") or {}
    if not rc.get("enabled"):
        return []
    layers = []
    for slug, t in (rc.get("types") or {}).items():
        name = Localized.from_any(t.get("name") or slug)
        if t.get("subtypes"):
            layers.extend((sub, st, (slug, name)) for sub, st in t["subtypes"].items())
        else:
            layers.append((slug, t, None))
    result = []
    for slug, t, parent in layers:
        kinds = set(t.get("kinds") or [])
        sel = [f for f in feats if f.kind in kinds and f.is_route]
        if not sel:
            log.info("route type %s: no routes, skipped", slug)
            continue
        xs = [c[0] for f in sel for c in f.all_coords()]
        ys = [c[1] for f in sel for c in f.all_coords()]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        bbox = {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}
        name = Localized.from_any(t.get("name") or slug)
        result.append((AreaDef(slug=slug, category=ROUTE_CATEGORY, name=name, tag=t.get("tag") or slug,
                               geometry=bbox), sel, parent))
    return result


def write_link_collections(settings: Settings, entries: list[dict], out_root: Path) -> dict:
    """Top-level KML files with network links to every area's KMZ.

    Per language: links/all_<lang>.kml (all categories, one folder each) and
    links/<category>_<lang>.kml (one category), each with a `_link.zip` package that adds
    it to ATAK as a refreshing link. Returns ({lang: {"all"|category: kml path}},
    {lang: {"all"|category: package path}}).
    """
    outs = settings.get("outputs") or {}
    if not (outs.get("kmz", True) and outs.get("network_link", True) and outs.get("root_links", True)):
        return {}, {}
    base_url = (settings.get("public_base_url") or "").rstrip("/")
    refresh = outs.get("network_link_refresh_s", 86400)
    visible_cfg = outs.get("root_links_visible") or {}
    result: dict[str, dict[str, str]] = {}
    packages: dict[str, dict[str, str]] = {}
    for lang in settings.languages:
        sections = []
        for category in sorted({e["category"] for e in entries if e["lang"] == lang},
                               key=category_sort_key(settings)):
            items = sorted((e for e in entries if e["lang"] == lang and e["category"] == category
                            and "kmz" in e["files"]), key=lambda e: (e.get("order", 0), e["name"]))
            if not items:
                continue
            links: list = []
            subfolders: dict[str, list] = {}
            for e in items:
                href = f"{base_url}/{e['files']['kmz']}"
                if e.get("parent"):   # route sub-layers in a subfolder of their type
                    if e["parent"] not in subfolders:
                        subfolders[e["parent"]] = []
                        links.append((e.get("parent_name") or e["parent"], subfolders[e["parent"]]))
                    subfolders[e["parent"]].append((e["name"], href))
                else:
                    links.append((e["name"], href))
            ctitle = _category_title(settings, category, lang)
            visible = bool(visible_cfg.get(category, True))
            if category != ROUTE_CATEGORY:   # parks and regions already contain their routes
                sections.append((ctitle, visible, links))
            path = out_root / "links" / f"{category}_{lang}.kml"
            kml.write_link_collection(path, f"Lipas – {ctitle}", [(ctitle, visible, links)], refresh)
            result.setdefault(lang, {})[category] = f"links/{path.name}"
            _link_package(outs, path, f"Lipas – {ctitle}", base_url, out_root, refresh, packages, lang, category)
        if sections:
            path = out_root / "links" / f"all_{lang}.kml"
            kml.write_link_collection(path, "Lipas", sections, refresh)
            result.setdefault(lang, {})["all"] = f"links/{path.name}"
            _link_package(outs, path, f"Lipas – {ALL_AREAS[lang]}", base_url, out_root, refresh, packages, lang, "all")
    return result, packages


ALL_AREAS = {"fi": "Kaikki alueet", "en": "All areas"}


def _link_package(outs: dict, kml_path: Path, name: str, base_url: str, out_root: Path, refresh: int,
                  packages: dict, lang: str, key: str) -> None:
    if not outs.get("link_package", True):
        return
    lp = kml_path.with_name(f"{kml_path.stem}_link.zip")
    remote_resource.write(lp, name, f"{base_url}/links/{kml_path.name}", refresh)
    packages.setdefault(lang, {})[key] = str(lp.relative_to(out_root))


# --- Change tracking --------------------------------------------------------------

def compare_with_previous(settings: Settings, prev_state: dict, entries: list[dict], kind_counts: dict[str, int],
                          empty: set[str]) -> list[str]:
    """Quality warnings against the previous build (cache/state.json).

    - an area (package) of the previous build is missing now, e.g. a park left
      Lipas or a source returned nothing (areas without features are already
      reported as such)
    - an area or a kind has far fewer features than before (quality.max_drop)
    """
    max_drop = float(settings.get("quality", "max_drop", default=0.3))
    min_compare = int(settings.get("quality", "min_compare", default=20))
    lang = settings.languages[0]
    prev_areas = {k.rsplit("/", 1)[0]: len(v) for k, v in (prev_state.get("areas") or {}).items()
                  if k.endswith(f"/{lang}")}
    cur_areas = {e["key"]: len(e["uids"]) for e in entries if e["lang"] == lang}
    out = []
    for key in sorted(set(prev_areas) - set(cur_areas) - empty):
        out.append(f"{key}: in the previous build but missing now, no package")

    def drop(name: str, before: int, now: int) -> None:
        if before >= min_compare and now < before * (1 - max_drop):
            out.append(f"{name}: {now} features, {before} in the previous build "
                       f"({(now - before) / before:.0%})")

    for key in sorted(set(prev_areas) & set(cur_areas)):
        drop(key, prev_areas[key], cur_areas[key])
    for kind, before in sorted((prev_state.get("kinds") or {}).items()):
        drop(f"kind {kind}", before, kind_counts.get(kind, 0))
    return out


def _load_state(state_path: Path) -> dict:
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {}


def diff_state(state_path: Path, entries: list[dict], now: datetime, times: Optional[dict] = None,
               kinds: Optional[dict[str, int]] = None) -> dict:
    """Compare with the previous run (UID -> content digest) and store the new state.

    `kinds`: feature count per kind (kept for the quality comparison of the next run).
    """
    cur = {f"{e['key']}/{e['lang']}": e["uids"] for e in entries}
    old_state = _load_state(state_path)
    prev = old_state.get("areas", {})
    changes = {}
    for key in sorted(set(cur) | set(prev)):
        a, b = prev.get(key, {}), cur.get(key, {})
        added = sorted(set(b) - set(a))
        removed = sorted(set(a) - set(b))
        modified = sorted(u for u in set(a) & set(b) if a[u] != b[u])
        if added or removed or modified:
            changes[key] = {"added": added, "removed": removed, "modified": modified}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    since = times if times is not None else old_state.get("since", {})
    live = {f"{k}:{u}" for k, uids in cur.items() for u in uids}
    since = {k: v for k, v in since.items() if k in live or k.split(":", 1)[0] not in cur}
    state = {"generated": now.isoformat(), "areas": cur, "since": since}
    if kinds is not None:
        state["kinds"] = kinds
    elif old_state.get("kinds"):
        state["kinds"] = old_state["kinds"]
    state_path.write_text(json.dumps(state), encoding="utf-8")
    log_path = state_path.parent / "changes.jsonl"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"generated": now.isoformat(), "changes": {
            k: {kk: len(vv) for kk, vv in v.items()} for k, v in changes.items()}}) + "\n")
    return changes


LANG_NAMES = {"fi": "Suomi", "en": "English"}


def render_index_html(index: dict) -> str:
    from html import escape
    base = (index.get("public_base_url") or "").rstrip("/")

    def url(rel: str) -> str:
        return f"{base}/{rel}" if base else rel

    link_rows = []
    for lang, links in sorted((index.get("links") or {}).items()):
        items = []
        for key, rel in sorted(links.items(), key=lambda kv: (kv[0] != "all", kv[0])):
            label = "All areas" if key == "all" else key
            pkg = ((index.get("link_packages") or {}).get(lang) or {}).get(key)
            items.append(f"<li><a href='{escape(rel)}'>{escape(label)}</a> "
                         + (f"(<a href='{escape(pkg)}'>ATAK package</a>) " if pkg else "")
                         + f"<code>{escape(url(rel))}</code></li>")
        link_rows.append(f"<h3>{escape(LANG_NAMES.get(lang, lang))}</h3><ul>{''.join(items)}</ul>")

    rows = []
    for e in sorted(index["areas"], key=lambda e: (e["lang"], e["category"], e["name"])):
        links = " ".join(f'<a href="{escape(v)}">{escape(k)}</a>' for k, v in sorted(e["files"].items()))
        total = sum(e["counts"].values())
        rows.append(f"<tr><td>{escape(e['lang'])}</td><td>{escape(e['category'])}</td>"
                    f"<td>{escape(e['name'])}</td><td>{total}</td><td>{links}</td></tr>")
    return (
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Lipas → TAK</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:16px;max-width:1100px}"
        "table{border-collapse:collapse;width:100%}"
        "td,th{border-bottom:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}"
        "td a{margin-right:.6em;white-space:nowrap}code{font-size:.85em;color:#555;word-break:break-all}"
        ".note{background:#f4f6f8;padding:8px 12px;border-radius:6px}</style>"
        f"<h1>Lipas → TAK</h1><p>Data checked {escape(index['generated'][:10])}"
        + (f", checked about every {round((datetime.fromisoformat(index['next_check']) - datetime.fromisoformat(index['generated'])).total_seconds() / 86400)} days" if index.get("next_check") else "") + ". "
        f"Icon set (install once): <a href='{escape(index['iconset'])}'>lipas2tak_iconset.zip</a></p>"
        + (("<p><b>QR codes / share pages:</b> " + " · ".join(
            f"<a href='{escape(pages[0])}'>{escape(LANG_NAMES.get(lang, lang))}</a>"
            for lang, pages in sorted(index["share"].items())) + "</p>") if index.get("share") else "")
        + "<h2>KML network links</h2>"
        "<p><b>ATAK:</b> Import → <i>KML Link</i> → paste one of the URLs below and turn on auto refresh "
        "(e.g. 86400 s). The areas appear as child links in Overlay Manager → Network Resources, "
        "where they can be switched on and off. A single area works the same way with its "
        "<i>kmz</i> URL from the table below. "
        "<b>WinTAK / Google Earth:</b> open the <code>.kml</code> file.</p>"
        + "".join(link_rows) +
        "<p class='note'>KML/KMZ layers are overlays: good for an overview without a server, "
        "but routes are plain lines and hashtag search does not cover them. For navigable routes and "
        "hashtag filtering use the data packages (<i>datapackage</i>) or TAK Server Data Sync.</p>"
        "<h2>All files</h2>"
        "<table><tr><th>Lang</th><th>Type</th><th>Area</th><th>Features</th><th>Files</th></tr>"
        + "".join(rows) + "</table>"
        f"<p><small>Data licence: <a href='{escape(index['license_url'])}'>ODbL 1.0</a>. "
        f"{' · '.join(escape(a) for a in index['attribution'])}</small></p></html>"
    )

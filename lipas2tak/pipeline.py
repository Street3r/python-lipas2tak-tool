"""Koko ajo: haku -> normalisointi -> rikastus -> tuotokset -> index.json."""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import areas as areas_mod
from . import normalize, remarks
from .config import Settings, file_slug
from .model import AreaDef, Feature
from .sources import lipas, osm, regions
from .sources.http import CachedClient
from .writers import cot, datapackage, gpx, iconset, kml

log = logging.getLogger(__name__)


# --- Raakadata --------------------------------------------------------------

@dataclass
class RawData:
    sites: list[dict] = field(default_factory=list)              # Lipas sports-sites
    lois: list[dict] = field(default_factory=list)               # Lipas LOIt
    osm: dict[str, list[dict]] = field(default_factory=dict)     # kind -> OSM-elementit
    area_sites: dict[str, list[dict]] = field(default_factory=dict)  # kategoria -> Lipas-aluekohteet
    regions: list[dict] = field(default_factory=list)            # GeoJSON-featuret

    FILES = ("sites", "lois", "osm", "area_sites", "regions")

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
        for kind, tags in clf.osm_queries():
            try:
                raw.osm[kind] = osm.fetch(client, oc["overpass_url"], tags)
            except Exception as e:  # OSM on täydentävä lähde: virhe ei kaada ajoa
                log.error("OSM-haku epäonnistui (%s): %s", kind, e)
    if (settings.get("areas", "maakunnat") or {}).get("enabled"):
        rc = settings.get("sources", "regions")
        data = client.get_json(rc["wfs_url"], params={
            "service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeName": rc["layer"],
            "outputFormat": "application/json", "srsName": "EPSG:4326"})
        raw.regions = data.get("features", [])
    return raw


# --- Rikastus -----------------------------------------------------------------

def build_features(settings: Settings, raw: RawData, clf: normalize.Classifier
                   ) -> tuple[list[Feature], dict[str, AreaDef]]:
    feats: list[Feature] = []
    for s in raw.sites:
        feats.extend(normalize.lipas_site_to_features(s, clf, settings))
    for l in raw.lois:
        f = normalize.loi_to_feature(l, clf)
        if f:
            feats.append(f)
    # Sama UID kahdesti (esim. sivutuksen päällekkäisyys) -> viimeinen voittaa
    feats = list({f.uid: f for f in feats}.values())

    oc = settings.get("sources", "osm") or {}
    for kind, els in raw.osm.items():
        cand = [f for f in (normalize.osm_to_feature(e, kind) for e in els) if f]
        kept = normalize.dedupe_osm(cand, feats, context_radius_m=oc.get("context_radius_m", 300),
                                    dedupe_radius_m=oc.get("dedupe_radius_m", 40))
        log.info("OSM %s: %d/%d otettu mukaan", kind, len(kept), len(cand))
        feats.extend(kept)

    all_areas: dict[str, AreaDef] = {}
    for cat, sites in raw.area_sites.items():
        defs = areas_mod.areas_from_lipas_sites(sites, cat, settings.get("areas", cat),
                                                settings.area_names.get(cat))
        areas_mod.assign_areas(feats, defs)
        all_areas.update({a.key: a for a in defs})
    if raw.regions:
        regs = regions.fetch_regions_from_features(raw.regions)
        areas_mod.assign_regions(feats, regs)
        all_areas.update({r.key: r for r in regs})
    return feats, all_areas


# --- Tuotokset ------------------------------------------------------------------

def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _route_parts(f: Feature) -> list[tuple[str, list]]:
    if len(f.lines) == 1:
        return [(f.uid, f.lines[0])]
    return [(f"{f.uid}-{i}", l) for i, l in enumerate(f.lines, 1)]


def write_area(settings: Settings, area: AreaDef, feats: list[Feature], all_areas: dict[str, AreaDef],
               out_root: Path, now: datetime) -> list[dict]:
    """Kirjoittaa yhden alueen tuotokset kaikilla kielillä. Palauttaa index-merkinnät."""
    kinds = settings.kinds
    icons_dir = settings.path("icons")
    outs = settings.get("outputs") or {}
    stroke = float(settings.get("routes", "stroke_weight", default=4.0))
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
        folders: dict[str, kml.Folder] = {}
        icon_styles: dict[str, str] = {}
        line_styles: dict[str, tuple[str, float]] = {}
        gpx_files: list[tuple[str, str]] = []

        for f in feats:
            k = kinds[f.kind]
            name = remarks.display_name(f, k, lang)
            rem = remarks.remarks(f, k, lang, all_areas, settings)
            folder = folders.setdefault(k.group, kml.Folder(settings.groups[k.group]["label"][lang]))
            if f.is_route:
                parts = _route_parts(f)
                for uid, line in parts:
                    xml = cot.polyline(uid, line, name, rem, k.color or "#FF0000", stroke, now=now)
                    cot_items.append((uid, name, xml))
                    uid_digests[uid] = _digest(name + rem + repr(line))
                line_styles[f"s-{k.key}"] = (k.color or "#FF0000", stroke)
                folder.placemarks.append(kml.Placemark(f.uid, name, rem, f"s-{k.key}", lines=f.lines))
                gpx_files.append((f"{file_slug(name) or f.uid}_{f.uid}.gpx",
                                  gpx.route_gpx(name, rem, f.lines, f.www)))
            else:
                assert f.point
                path = iconset.iconsetpath(k.icon) if k.icon else None
                xml = cot.marker(f.uid, k.cot_type, f.point[1], f.point[0], name, rem, path, now=now)
                cot_items.append((f.uid, name, xml))
                uid_digests[f.uid] = _digest(name + rem + repr(f.point))
                if k.icon:
                    icon_styles[f"s-{k.key}"] = k.icon
                folder.placemarks.append(kml.Placemark(f.uid, name, rem, f"s-{k.key}", point=f.point))

        if outs.get("datapackage", True) and cot_items:
            p = d / f"{stem}.zip"
            datapackage.write(p, f"{title} ({lang})", f"{area.key}/{lang}", cot_items)
            files["datapackage"] = str(p.relative_to(out_root))
        if outs.get("kmz", True) and cot_items:
            p = d / f"{stem}.kmz"
            kml.write_kmz(p, title, list(folders.values()), icon_styles, line_styles, icons_dir)
            files["kmz"] = str(p.relative_to(out_root))
            if outs.get("network_link", True):
                nl = d / f"{stem}.kml"
                kml.write_network_link(nl, title, f"{base_url}/{files['kmz']}", outs.get("network_link_refresh_s", 86400))
                files["network_link"] = str(nl.relative_to(out_root))
            if outs.get("kmz_per_group", True):
                for group, folder in folders.items():
                    if not folder.placemarks:
                        continue
                    gname = f"{title} – {settings.groups[group]['label'][lang]}"
                    p = d / f"{stem}_{group}.kmz"
                    kml.write_kmz(p, gname, [folder], icon_styles, line_styles, icons_dir)
                    files[f"kmz_{group}"] = str(p.relative_to(out_root))
                    if outs.get("network_link", True):
                        nl = d / f"{stem}_{group}.kml"
                        kml.write_network_link(nl, gname, f"{base_url}/{files[f'kmz_{group}']}",
                                               outs.get("network_link_refresh_s", 86400))
                        files[f"network_link_{group}"] = str(nl.relative_to(out_root))
        if outs.get("gpx", True) and gpx_files:
            p = d / f"{stem}_gpx.zip"
            gpx.write_zip(p, gpx_files)
            files["gpx_zip"] = str(p.relative_to(out_root))

        counts: dict[str, int] = {}
        for f in feats:
            counts[f.kind] = counts.get(f.kind, 0) + 1
        entries.append({
            "key": area.key, "category": area.category, "slug": area.slug, "lang": lang,
            "name": title, "tag": area.tag, "files": files, "counts": counts,
            "uids": uid_digests,
        })
    return entries


def run(settings: Settings, raw: RawData, only: Optional[list[str]] = None,
        now: Optional[datetime] = None) -> dict:
    """Tuottaa kaikki tiedostot. `only`: rajaus alueavaimiin (esim. kansallispuistot/nuuksio)."""
    now = now or datetime.now(timezone.utc)
    clf = normalize.Classifier(settings)
    feats, all_areas = build_features(settings, raw, clf)
    out_root = settings.path("output")
    staging = out_root.parent / (out_root.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    used_icons = [k.icon for k in settings.enabled_kinds() if k.icon]
    iconset.write(staging / "iconset" / "lipas2tak_iconset.zip", settings.path("icons"), used_icons)

    index_areas = []
    targets = [a for a in all_areas.values() if not only or a.key in only or a.slug in only]
    for area in sorted(targets, key=lambda a: (a.category, a.slug)):
        if area.category == "maakunnat":
            sel = [f for f in feats if f.region == area.key]
        else:
            sel = [f for f in feats if area.key in f.areas]
        if not sel:
            log.info("%s: ei kohteita, ohitetaan", area.key)
            continue
        index_areas.extend(write_area(settings, area, sel, all_areas, staging, now))

    index = {
        "generated": now.isoformat(),
        "public_base_url": settings.get("public_base_url"),
        "iconset": "iconset/lipas2tak_iconset.zip",
        "iconset_uid": iconset.ICONSET_UID,
        "attribution": [
            "Lipas – Jyväskylän yliopisto (lipas.fi)",
            "© OpenStreetMap contributors (ODbL)",
            "Maakuntarajat: Tilastokeskus (CC BY 4.0)",
        ],
        "areas": index_areas,
    }
    (staging / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    (staging / "index.html").write_text(render_index_html(index), encoding="utf-8")

    changes = diff_state(settings.path("cache") / "state.json", index_areas, now)
    # Atominen vaihto: vanhat (poistuneet) tiedostot katoavat samalla
    old = out_root.parent / (out_root.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if out_root.exists():
        out_root.rename(old)
    staging.rename(out_root)
    if old.exists():
        shutil.rmtree(old)
    log.info("Valmis: %d aluetta, %d kohdetta", len({e['key'] for e in index_areas}), len(feats))
    return {"index": index, "changes": changes, "features": len(feats)}


# --- Muutosseuranta ---------------------------------------------------------------

def diff_state(state_path: Path, entries: list[dict], now: datetime) -> dict:
    """Vertaa edelliseen ajoon (UID -> sisällön tiiviste) ja tallentaa uuden tilan."""
    cur = {f"{e['key']}/{e['lang']}": e["uids"] for e in entries}
    prev = {}
    if state_path.exists():
        prev = json.loads(state_path.read_text(encoding="utf-8")).get("areas", {})
    changes = {}
    for key in sorted(set(cur) | set(prev)):
        a, b = prev.get(key, {}), cur.get(key, {})
        added = sorted(set(b) - set(a))
        removed = sorted(set(a) - set(b))
        modified = sorted(u for u in set(a) & set(b) if a[u] != b[u])
        if added or removed or modified:
            changes[key] = {"added": added, "removed": removed, "modified": modified}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"generated": now.isoformat(), "areas": cur}), encoding="utf-8")
    log_path = state_path.parent / "changes.jsonl"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"generated": now.isoformat(), "changes": {
            k: {kk: len(vv) for kk, vv in v.items()} for k, v in changes.items()}}) + "\n")
    return changes


def render_index_html(index: dict) -> str:
    from html import escape
    base = (index.get("public_base_url") or "").rstrip("/")
    rows = []
    for e in sorted(index["areas"], key=lambda e: (e["lang"], e["category"], e["slug"])):
        links = " ".join(f'<a href="{escape(v)}">{escape(k)}</a>' for k, v in sorted(e["files"].items()))
        total = sum(e["counts"].values())
        rows.append(f"<tr><td>{escape(e['lang'])}</td><td>{escape(e['category'])}</td>"
                    f"<td>{escape(e['name'])}</td><td>{total}</td><td>{links}</td></tr>")
    return (
        "<!doctype html><html lang='fi'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Lipas → TAK</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:16px}table{border-collapse:collapse;width:100%}"
        "td,th{border-bottom:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}"
        "a{margin-right:.6em;white-space:nowrap}</style>"
        f"<h1>Lipas → TAK</h1><p>Päivitetty {escape(index['generated'])}. "
        f"Kuvakesarja: <a href='{escape(index['iconset'])}'>lipas2tak_iconset.zip</a>. "
        f"KML-verkkolinkkien osoite: {escape(base)}</p>"
        "<table><tr><th>Kieli</th><th>Tyyppi</th><th>Alue</th><th>Kohteita</th><th>Tiedostot</th></tr>"
        + "".join(rows) + "</table>"
        f"<p><small>{' · '.join(escape(a) for a in index['attribution'])}</small></p></html>"
    )

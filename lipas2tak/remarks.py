"""CoT remarks / KML description / GPX desc texts per language, with hashtags."""
from __future__ import annotations

from .config import Kind, Settings
from .model import AreaDef, Feature

SERVICE_LABELS = {
    "toilet": {"fi": "WC", "en": "toilet"},
    "parking": {"fi": "pysäköinti", "en": "parking"},
    "water": {"fi": "vesipiste", "en": "water"},
    "rest_places": {"fi": "taukopaikkoja", "en": "rest stops"},
    "wheelchair": {"fi": "esteetön", "en": "wheelchair accessible"},
    "fireplace": {"fi": "tulipaikka", "en": "fire place"},
    "viewpoint": {"fi": "näköala", "en": "viewpoint"},
}

ADMIN_LABELS = {
    "state": {"fi": "valtio", "en": "state"},
    "city-sports": {"fi": "kunta", "en": "municipality"},
    "city-other": {"fi": "kunta", "en": "municipality"},
    "city-technical-services": {"fi": "kunta", "en": "municipality"},
    "city-education": {"fi": "kunta", "en": "municipality"},
    "private-association": {"fi": "yhdistys", "en": "association"},
    "private-foundation": {"fi": "säätiö", "en": "foundation"},
    "private-company": {"fi": "yritys", "en": "company"},
    "municipal-consortium": {"fi": "kuntayhtymä", "en": "joint municipal authority"},
    "other": {"fi": "muu", "en": "other"},
}

ACCESSIBILITY_LABELS = {
    "accessible": {"fi": "esteetön", "en": "accessible"},
    "advanced-accessible": {"fi": "vaativa esteetön", "en": "accessible (demanding)"},
    "inaccessible": {"fi": "ei esteetön", "en": "not accessible"},
}

T = {
    "services": {"fi": "Palvelut", "en": "Services"},
    "marking": {"fi": "Merkintä", "en": "Marking"},
    "accessibility": {"fi": "Esteettömyys", "en": "Accessibility"},
    "admin": {"fi": "Ylläpito", "en": "Maintained by"},
    "temp_closed": {"fi": "TILAPÄISESTI POISSA KÄYTÖSTÄ", "en": "TEMPORARILY OUT OF SERVICE"},
    "src_osm": {"fi": "Lähde: OpenStreetMap", "en": "Source: OpenStreetMap"},
    "network": {"fi": "Reitistö yhteensä {total} km, tämä osa {part} km",
                "en": "Trail network {total} km in total, this section {part} km"},
}


def _km(v: float, lang: str) -> str:
    return f"{v:.1f}".replace(".", "," if lang == "fi" else ".")


def _truncate(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def hashtags(f: Feature, kind: Kind, lang: str, areas: dict[str, AreaDef],
             kinds: dict[str, Kind] | None = None) -> list[str]:
    tags = [kind.tag.get(lang) or kind.tag["fi"]]
    for k in f.also_kinds:   # merged secondary kinds, e.g. a lean-to that is also a fire place
        if kinds and k in kinds:
            tags.append(kinds[k].tag.get(lang) or kinds[k].tag["fi"])
    for slug in f.areas:
        if slug in areas:
            tags.append(areas[slug].tag)
    if f.region and f.region in areas:
        tags.append(areas[f.region].tag)
    seen, out = set(), []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            out.append("#" + t)
    return out


def display_name(f: Feature, kind: Kind, lang: str) -> str:
    n = f.name.get(lang).strip() or (kind.label.get(lang) or kind.label["fi"])
    if f.network_km and f.length_km:
        # Sections of a path network share the name; the length tells them apart
        n = f"{n} · {_km(f.length_km, lang)} km"
    return n


def remarks(f: Feature, kind: Kind, lang: str, areas: dict[str, AreaDef], settings: Settings) -> str:
    parts: list[str] = []
    label = kind.label.get(lang) or kind.label["fi"]
    if f.status == "out-of-service-temporarily":
        parts.append(T["temp_closed"][lang])
    if f.is_route and f.network_km:
        parts.append(label)
        parts.append(T["network"][lang].format(total=_km(f.network_km, lang), part=_km(f.length_km or 0, lang)))
    elif f.is_route and f.length_km:
        parts.append(f"{label} {_km(f.length_km, lang)} km")
    else:
        parts.append(label)
    if f.marking.get(lang):
        parts.append(f"{T['marking'][lang]}: {f.marking.get(lang)}")
    if f.services:
        labels = [SERVICE_LABELS.get(s, {}).get(lang, s) for s in f.services]
        parts.append(f"{T['services'][lang]}: {', '.join(labels)}")
    acc = f.accessibility.get(lang)
    if acc:
        acc = ACCESSIBILITY_LABELS.get(acc, {}).get(lang, acc)
        parts.append(f"{T['accessibility'][lang]}: {acc}")
    if f.description.get(lang):
        parts.append(f.description.get(lang))
    if f.admin and f.admin in ADMIN_LABELS:
        parts.append(f"{T['admin'][lang]}: {ADMIN_LABELS[f.admin][lang]}")
    if f.source == "osm":
        parts.append(T["src_osm"][lang])
    text = _truncate(" · ".join(parts), int(settings.get("remarks", "max_text_chars", default=500)))
    if f.www:
        text += f" · {f.www}"
    return f"{text} {' '.join(hashtags(f, kind, lang, areas, settings.kinds))}".strip()

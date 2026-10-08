"""Share pages: QR codes and "open in ATAK" links for every file.

Writes share/<lang>/index.html (start page) and share/<lang>/<category>.html
(one page per area category), one language per page.

QR codes and links use ATAK's import URI
    tak://com.atakmap.app/import?url=<percent-encoded https url>
which ATAK opens after asking for confirmation. Plain https links are shown
for iTAK, WinTAK and browsers.
"""
from __future__ import annotations

import logging
from html import escape
from pathlib import Path
from urllib.parse import quote

log = logging.getLogger(__name__)

try:  # optional dependency: pages are written without QR images if missing
    import segno
except ImportError:  # pragma: no cover
    segno = None

ATAK_IMPORT = "tak://com.atakmap.app/import?url="

TEXT = {
    "en": {
        "title": "Finland outdoor TAK data",
        "all": "All areas",
        "lang_other": ("fi", "Suomeksi"),
        "intro": "Scan a QR code with the phone camera and open it with ATAK, or tap a button on the phone. "
                 "ATAK asks before importing. iTAK and WinTAK: use the download links.",
        "step1": "1. Icon set (install once)",
        "step1_text": "Without it the markers show default icons.",
        "step2": "2. All areas as auto-refreshing layers",
        "step2_text": "National parks are on by default, regions off. Switch areas on and off in "
                      "Overlay Manager → Network Resources. Or add the link by hand: Import → KML Link, "
                      "paste the URL, auto refresh 86400 s.",
        "step3": "3. One area at a time",
        "step3_text": "Data packages contain navigable routes with named waypoints and #hashtags for filtering.",
        "open": "Open in ATAK",
        "kml": "KML link",
        "package": "Data package",
        "downloads": "Downloads",
        "features": "features",
        "back": "Start",
        "catalogue": "All files",
        "kml_note": "KML layers are an overview: routes are plain lines and hashtag search does not cover them.",
        "licence": "Data licence",
        "no_qr": "",
    },
    "fi": {
        "title": "Suomen retkeilykohteet TAKiin",
        "all": "Kaikki alueet",
        "lang_other": ("en", "In English"),
        "intro": "Skannaa QR-koodi puhelimen kameralla ja avaa ATAKilla, tai paina painiketta puhelimella. "
                 "ATAK kysyy ennen tuontia. iTAK ja WinTAK: käytä latauslinkkejä.",
        "step1": "1. Kuvakesarja (asennetaan kerran)",
        "step1_text": "Ilman sitä merkit näkyvät oletuskuvakkeilla.",
        "step2": "2. Kaikki alueet päivittyvinä tasoina",
        "step2_text": "Kansallispuistot ovat oletuksena päällä ja maakunnat pois. Alueet valitaan "
                      "Overlay Managerin kohdasta Network Resources. Linkin voi lisätä myös käsin: "
                      "Import → KML Link, liitä osoite, automaattinen päivitys 86400 s.",
        "step3": "3. Yksi alue kerrallaan",
        "step3_text": "Datapaketeissa on navigoitavat reitit nimettyine reittipisteineen ja #hashtagit suodatukseen.",
        "open": "Avaa ATAKissa",
        "kml": "KML-linkki",
        "package": "Datapaketti",
        "downloads": "Lataukset",
        "features": "kohdetta",
        "back": "Alku",
        "catalogue": "Kaikki tiedostot",
        "kml_note": "KML-tasot ovat yleiskuva: reitit näkyvät viivoina, eikä hashtag-haku löydä niitä.",
        "licence": "Aineiston lisenssi",
        "no_qr": "",
    },
}

CSS = (
    ":root{color-scheme:light dark;--fg:#1d2329;--muted:#5b6670;--bg:#fff;--card:#f3f5f7;--accent:#1f6f4a;--btn-fg:#fff}"
    "@media (prefers-color-scheme:dark){:root{--fg:#e7ecef;--muted:#9aa7b1;--bg:#14181b;--card:#1f2529;--accent:#5cc28f;--btn-fg:#0d1f16}}"
    "*{box-sizing:border-box}body{font-family:system-ui,sans-serif;margin:0 auto;padding:16px;max-width:980px;"
    "color:var(--fg);background:var(--bg);line-height:1.45}"
    "a{color:var(--accent)}nav{display:flex;gap:14px;flex-wrap:wrap;font-size:.95em;margin-bottom:8px}"
    "h1{font-size:1.5em;margin:.3em 0}h2{font-size:1.15em;margin:1.4em 0 .4em}.muted{color:var(--muted)}"
    ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px}"
    ".card{background:var(--card);border-radius:10px;padding:12px}.card h3{margin:0 0 4px;font-size:1.02em}"
    ".qrs{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}.qr{text-align:center;font-size:.85em}"
    ".qr svg{display:block;width:132px;height:132px;border-radius:4px}"
    ".btn{display:inline-block;padding:6px 10px;border-radius:6px;background:var(--accent);color:var(--btn-fg);font-weight:600;"
    "text-decoration:none;font-size:.9em;margin:2px 4px 2px 0}"
    ".dl a{margin-right:10px;font-size:.9em}code{font-size:.8em;word-break:break-all;color:var(--muted)}"
    "footer{margin-top:2em;font-size:.8em;color:var(--muted)}"
)


def atak_uri(url: str) -> str:
    return ATAK_IMPORT + quote(url, safe="")


def qr_svg(payload: str) -> str:
    if segno is None:
        return ""
    return segno.make(payload, error="m").svg_inline(scale=3, border=3, dark="#000", light="#fff", omitsize=True)


def _qr_block(label: str, url: str) -> str:
    uri = atak_uri(url)
    svg = qr_svg(uri)
    return (f"<div class='qr'>{svg}<a class='btn' href='{escape(uri)}'>{escape(label)}</a></div>")


def _page(lang: str, title: str, body: str, nav: str, attribution: list[str], licence_url: str) -> str:
    t = TEXT[lang]
    return (
        f"<!doctype html><html lang='{lang}'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title><style>{CSS}</style><body>"
        f"<nav>{nav}</nav>{body}"
        f"<footer>{escape(t['licence'])}: <a href='{escape(licence_url)}'>ODbL 1.0</a> · "
        f"{' · '.join(escape(a) for a in attribution)}</footer></body></html>\n"
    )


def write_share_pages(out_root: Path, index: dict, category_titles: dict[str, dict[str, str]],
                      languages: list[str]) -> dict[str, list[str]]:
    """Write the share pages. Returns {lang: [relative page paths]}."""
    base = (index.get("public_base_url") or "").rstrip("/")
    if not base:
        log.warning("No public_base_url: share pages skipped")
        return {}
    if segno is None:
        log.warning("segno not installed: share pages without QR codes")

    def url(rel: str) -> str:
        return f"{base}/{rel}"

    written: dict[str, list[str]] = {}
    for lang in languages:
        t = TEXT[lang]
        d = out_root / "share" / lang
        d.mkdir(parents=True, exist_ok=True)
        entries = [e for e in index["areas"] if e["lang"] == lang]
        categories = sorted({e["category"] for e in entries})
        links = (index.get("links") or {}).get(lang, {})
        other_lang, other_label = t["lang_other"]

        def nav(current: str) -> str:
            items = [f"<a href='index.html'>{escape(t['back'])}</a>"]
            for c in categories:
                ctitle = category_titles.get(c, {}).get(lang, c)
                items.append(f"<b>{escape(ctitle)}</b>" if c == current
                             else f"<a href='{c}.html'>{escape(ctitle)}</a>")
            items.append(f"<a href='../../index.html'>{escape(t['catalogue'])}</a>")
            if other_lang in languages:
                target = "index.html" if current == "index" else f"{current}.html"
                items.append(f"<a href='../{other_lang}/{target}'>{escape(other_label)}</a>")
            return "".join(items)

        # Start page
        body = [f"<h1>{escape(t['title'])}</h1><p class='muted'>{escape(t['intro'])}</p>"]
        body.append(f"<h2>{escape(t['step1'])}</h2><p>{escape(t['step1_text'])}</p>"
                    f"<div class='qrs'>{_qr_block(t['open'], url(index['iconset']))}</div>"
                    f"<p class='dl'><a href='{escape(url(index['iconset']))}'>lipas2tak_iconset.zip</a></p>")
        if links:
            cards = []
            for key in ["all"] + [c for c in categories if c in links]:
                if key not in links:
                    continue
                label = (t["all"] if key == "all"
                         else category_titles.get(key, {}).get(lang, key))
                cards.append(f"<div class='card'><h3>{escape(label)}</h3>"
                             f"<div class='qrs'>{_qr_block(t['open'], url(links[key]))}</div>"
                             f"<code>{escape(url(links[key]))}</code></div>")
            body.append(f"<h2>{escape(t['step2'])}</h2><p>{escape(t['step2_text'])}</p>"
                        f"<p class='muted'>{escape(t['kml_note'])}</p><div class='grid'>{''.join(cards)}</div>")
        cat_links = " · ".join(
            f"<a href='{c}.html'>{escape(category_titles.get(c, {}).get(lang, c))}</a>" for c in categories)
        body.append(f"<h2>{escape(t['step3'])}</h2><p>{escape(t['step3_text'])}</p><p>{cat_links}</p>")
        (d / "index.html").write_text(
            _page(lang, t["title"], "".join(body), nav("index"), index["attribution"], index["license_url"]),
            encoding="utf-8")
        pages = [f"share/{lang}/index.html"]

        # One page per category
        for c in categories:
            ctitle = category_titles.get(c, {}).get(lang, c)
            cards = []
            for e in sorted((e for e in entries if e["category"] == c), key=lambda e: e["name"]):
                files = e["files"]
                total = sum(e["counts"].values())
                qrs = []
                if "datapackage" in files:
                    qrs.append(_qr_block(f"{t['package']} → ATAK", url(files["datapackage"])))
                if "network_link" in files:
                    qrs.append(_qr_block(f"{t['kml']} → ATAK", url(files["network_link"])))
                dls = [f"<a href='{escape(url(files[k]))}'>{label}</a>"
                       for k, label in (("datapackage", ".zip"), ("kmz", ".kmz"), ("network_link", ".kml"),
                                        ("gpx_zip", "GPX")) if k in files]
                cards.append(
                    f"<div class='card' id='{escape(e['slug'])}'><h3>{escape(e['name'])}</h3>"
                    f"<span class='muted'>{total} {escape(t['features'])} · #{escape(e['tag'])}</span>"
                    f"<div class='qrs'>{''.join(qrs)}</div>"
                    f"<p class='dl'>{escape(t['downloads'])}: {''.join(dls)}</p></div>")
            body = (f"<h1>{escape(ctitle)}</h1><p class='muted'>{escape(t['intro'])}</p>"
                    f"<div class='grid'>{''.join(cards)}</div>")
            (d / f"{c}.html").write_text(
                _page(lang, f"{ctitle} – {t['title']}", body, nav(c), index["attribution"], index["license_url"]),
                encoding="utf-8")
            pages.append(f"share/{lang}/{c}.html")
        written[lang] = pages
    return written

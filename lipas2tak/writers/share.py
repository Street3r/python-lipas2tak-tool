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
        "step2_text": "Scan the QR code or tap the button on the phone: ATAK adds an auto-refreshing link "
                      "(Overlay Manager → Network Resources), refreshed daily. National parks, wilderness areas and "
                      "state hiking areas are on by default and regions off (they contain the same sites too); "
                      "switch regions on one by one. Other apps: "
                      "download the .kml file or copy its URL.",
        "add_link": "Add to ATAK",
        "layer": "Auto-refreshing layer",
        "copy": "Copy URL",
        "copied": "Copied",
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
        "search": "Search areas…",
        "updated": "updated",
        "checked": "Data checked",
        "interval": "data is checked about every {n} days",
        "checked_note": "Each area shows the date of its latest change.",
        "search_all": "Find an area",
        "sort": "Sort",
        "sort_name": "Name A–Z",
        "sort_most": "Most features",
        "sort_least": "Fewest features",
        "no_results": "No matching areas.",
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
        "step2_text": "Skannaa QR-koodi tai paina painiketta puhelimella: ATAK lisää päivittyvän linkin "
                      "(Overlay Manager → Network Resources), joka päivittyy kerran vuorokaudessa. "
                      "Kansallispuistot, erämaa-alueet ja valtion retkeilyalueet ovat oletuksena päällä ja maakunnat "
                      "pois (niissä ovat samat kohteet); "
                      "ota maakunnat käyttöön yksitellen. Muut sovellukset: lataa .kml-tiedosto tai kopioi osoite.",
        "add_link": "Lisää ATAKiin",
        "layer": "Päivittyvä taso",
        "copy": "Kopioi osoite",
        "copied": "Kopioitu",
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
        "search": "Hae aluetta…",
        "updated": "päivitetty",
        "checked": "Tiedot tarkistettu",
        "interval": "tietoja tarkistetaan arviolta {n} päivän välein",
        "checked_note": "Alueen kohdalla näkyy sen viimeisimmän muutoksen päivä.",
        "search_all": "Etsi alue",
        "sort": "Järjestys",
        "sort_name": "Nimi A–Ö",
        "sort_most": "Eniten kohteita",
        "sort_least": "Vähiten kohteita",
        "no_results": "Ei hakua vastaavia alueita.",
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
    ".tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:12px 0;position:sticky;top:0;"
    "background:var(--bg);padding:8px 0;z-index:1}"
    ".tools input,.tools select{font:inherit;padding:8px 10px;border-radius:8px;border:1px solid var(--muted);"
    "background:var(--card);color:var(--fg)}.tools input{flex:1;min-width:200px}"
    ".card:target{outline:3px solid var(--accent)}.hits{list-style:none;padding:0;margin:6px 0;columns:2 220px}"
    ".hits li{margin:3px 0}[hidden]{display:none!important}"
)


# Client-side search and sort; the page works without it (all areas shown)
SEARCH_JS = """<script>
(function(){
  const norm = s => s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();
  const q = document.getElementById('q'), sort = document.getElementById('sort');
  const grid = document.getElementById('areas'), none = document.getElementById('none');
  const items = Array.from(document.querySelectorAll('[data-search]'));
  function apply(){
    const words = norm(q.value).split(/\\s+/).filter(Boolean);
    let shown = 0;
    items.forEach(el => {
      const ok = words.every(w => el.dataset.search.includes(w));
      el.hidden = !ok; if (ok) shown++;
    });
    if (none) none.hidden = shown > 0 || !words.length && !items.length;
    if (sort && grid) {
      const key = sort.value;
      const cards = items.filter(el => el.parentNode === grid);
      cards.sort((a,b) => key === 'name' ? a.dataset.name.localeCompare(b.dataset.name, document.documentElement.lang)
        : (key === 'most' ? b.dataset.count - a.dataset.count : a.dataset.count - b.dataset.count));
      cards.forEach(c => grid.appendChild(c));
    }
  }
  q.addEventListener('input', apply); if (sort) sort.addEventListener('change', apply);
  const p = new URLSearchParams(location.search).get('q'); if (p) { q.value = p; }
  apply();
})();
</script>"""


# Start page: list matches only while something is typed
START_SEARCH_JS = """<script>
(function(){
  const norm = s => s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();
  const q = document.getElementById('q'), none = document.getElementById('none');
  const items = Array.from(document.querySelectorAll('.hits [data-search]'));
  q.addEventListener('input', () => {
    const words = norm(q.value).split(/\\s+/).filter(Boolean);
    let shown = 0;
    items.forEach(el => { const ok = words.length > 0 && words.every(w => el.dataset.search.includes(w));
                          el.hidden = !ok; if (ok) shown++; });
    none.hidden = !words.length || shown > 0;
  });
})();
</script>"""


# Reads status.json (written on every run) so the pages themselves need not change
CHECKED_JS = """<script>
fetch('../../status.json', {cache: 'no-store'}).then(r => r.json()).then(s => {
  const loc = document.documentElement.lang === 'en' ? 'en-GB' : 'fi-FI';
  const line = document.getElementById('checked-line');
  const checked = new Date(s.checked);
  document.getElementById('checked').textContent = checked.toLocaleDateString(loc);
  if (s.next_check) {
    const days = Math.round((new Date(s.next_check) - checked) / 86400000);
    document.getElementById('next').textContent = line.dataset.interval.replace('{n}', days);
    document.getElementById('next-wrap').hidden = false;
  }
  document.getElementById('checked-line').hidden = false;
}).catch(() => {});
</script>"""


def _fmt_date(iso: str, lang: str) -> str:
    if not iso:
        return ""
    y, m, d = iso.split("-")
    return f"{int(d)}.{int(m)}.{y}" if lang == "fi" else iso


def _norm(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c)).lower()


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


COPY_JS = """<script>
document.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', e => {
  e.preventDefault();
  const done = () => { const t = b.textContent; b.textContent = b.dataset.done; setTimeout(() => b.textContent = t, 1500); };
  if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(b.dataset.copy).then(done);
  else { const a = document.createElement('textarea'); a.value = b.dataset.copy; document.body.appendChild(a);
         a.select(); document.execCommand('copy'); a.remove(); done(); }
}));
</script>"""


def _link_block(label: str, url: str, copied: str) -> str:
    """KML network link: ATAK only creates a refreshing link by hand (Import → KML Link),
    so the QR code holds the plain URL and the button copies it."""
    return (f"<div class='qr'>{qr_svg(url)}<a class='btn' href='{escape(url)}' data-copy='{escape(url)}' "
            f"data-done='{escape(copied)}'>{escape(label)}</a></div>")


def _copy_link(label: str, url: str, copied: str) -> str:
    """Plain download link and a copy button for a URL (for other apps or adding by hand)."""
    return (f"<a href='{escape(url)}'>{escape(url.rsplit('/', 1)[-1])}</a>"
            f"<a href='{escape(url)}' data-copy='{escape(url)}' data-done='{escape(copied)}'>{escape(label)}</a>")


def _page(lang: str, title: str, body: str, nav: str, attribution: list[str], licence_url: str) -> str:
    t = TEXT[lang]
    return (
        f"<!doctype html><html lang='{lang}'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title><style>{CSS}</style><body>"
        f"<nav>{nav}</nav>"
        f"<p class='muted' id='checked-line' data-interval='{escape(t['interval'])}' hidden>{escape(t['checked'])}: <b id='checked'></b>"
        f"<span id='next-wrap' hidden>, <span id='next'></span></span>. "
        f"{escape(t['checked_note'])}</p>{body}{COPY_JS}"
        + CHECKED_JS
        + f"<footer>{escape(t['licence'])}: <a href='{escape(licence_url)}'>ODbL 1.0</a> · "
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
        # category_titles is in display order (config.yaml)
        present = {e["category"] for e in entries}
        categories = [c for c in category_titles if c in present] + sorted(present - set(category_titles))
        links = (index.get("links") or {}).get(lang, {})
        link_pkgs = (index.get("link_packages") or {}).get(lang, {})
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
                upd = max((e.get("updated", "") for e in entries if key == "all" or e["category"] == key),
                          default="")
                pkg = link_pkgs.get(key)
                qr = (_qr_block(t["add_link"], url(pkg)) if pkg
                      else _link_block(t["copy"], url(links[key]), t["copied"]))
                cards.append(f"<div class='card'><h3>{escape(label)}</h3>"
                             + (f"<span class='muted'>{escape(t['updated'])} {_fmt_date(upd, lang)}</span>"
                                if upd else "")
                             + f"<div class='qrs'>{qr}</div>"
                             f"<p class='dl'>{_copy_link(t['copy'], url(links[key]), t['copied'])}</p></div>")
            body.append(f"<h2>{escape(t['step2'])}</h2><p>{escape(t['step2_text'])}</p>"
                        f"<p class='muted'>{escape(t['kml_note'])}</p><div class='grid'>{''.join(cards)}</div>")
        cat_links = " · ".join(
            f"<a href='{c}.html'>{escape(category_titles.get(c, {}).get(lang, c))}</a>" for c in categories)
        hits = "".join(
            f"<li data-search='{escape(_norm(e['name'] + ' ' + e['slug'] + ' ' + e['tag']))}' hidden>"
            f"<a href='{e['category']}.html#{escape(e['slug'])}'>{escape(e['name'])}</a> "
            f"<span class='muted'>· {escape(category_titles.get(e['category'], {}).get(lang, e['category']))}</span></li>"
            for e in sorted(entries, key=lambda e: e["name"]))
        body.append(f"<h2>{escape(t['step3'])}</h2><p>{escape(t['step3_text'])}</p><p>{cat_links}</p>"
                    f"<div class='tools'><input id='q' type='search' placeholder='{escape(t['search'])}' "
                    f"aria-label='{escape(t['search_all'])}' autocomplete='off'></div>"
                    f"<ul class='hits'>{hits}</ul><p id='none' class='muted' hidden>{escape(t['no_results'])}</p>"
                    + START_SEARCH_JS)
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
                if "link_package" in files:
                    qrs.append(_qr_block(f"{t['layer']} → ATAK", url(files["link_package"])))
                elif "network_link" in files:
                    qrs.append(_link_block(f"{t['kml']}: {t['copy']}", url(files["network_link"]), t["copied"]))
                dls = [f"<a href='{escape(url(files[k]))}'>{label}</a>"
                       for k, label in (("datapackage", ".zip"), ("kmz", ".kmz"), ("network_link", ".kml"),
                                        ("gpx_zip", "GPX")) if k in files]
                if "network_link" in files:
                    nl = url(files["network_link"])
                    dls.append(f"<a href='{escape(nl)}' data-copy='{escape(nl)}' data-done='{escape(t['copied'])}'>"
                               f"{escape(t['kml'])}: {escape(t['copy'])}</a>")
                search = _norm(f"{e['name']} {e['slug']} {e['tag']}")
                cards.append(
                    f"<div class='card' id='{escape(e['slug'])}' data-search='{escape(search)}' "
                    f"data-name='{escape(e['name'])}' data-count='{total}'><h3>{escape(e['name'])}</h3>"
                    f"<span class='muted'>{total} {escape(t['features'])} · #{escape(e['tag'])}"
                    + (f" · {escape(t['updated'])} {_fmt_date(e.get('updated', ''), lang)}" if e.get("updated") else "")
                    + "</span>"
                    f"<div class='qrs'>{''.join(qrs)}</div>"
                    f"<p class='dl'>{escape(t['downloads'])}: {''.join(dls)}</p></div>")
            tools = (f"<div class='tools'><input id='q' type='search' placeholder='{escape(t['search'])}' "
                     f"aria-label='{escape(t['search'])}' autocomplete='off'>"
                     f"<select id='sort' aria-label='{escape(t['sort'])}'>"
                     f"<option value='name'>{escape(t['sort_name'])}</option>"
                     f"<option value='most'>{escape(t['sort_most'])}</option>"
                     f"<option value='least'>{escape(t['sort_least'])}</option></select></div>")
            body = (f"<h1>{escape(ctitle)}</h1><p class='muted'>{escape(t['intro'])}</p>{tools}"
                    f"<div class='grid' id='areas'>{''.join(cards)}</div>"
                    f"<p id='none' class='muted' hidden>{escape(t['no_results'])}</p>{SEARCH_JS}")
            (d / f"{c}.html").write_text(
                _page(lang, f"{ctitle} – {t['title']}", body, nav(c), index["attribution"], index["license_url"]),
                encoding="utf-8")
            pages.append(f"share/{lang}/{c}.html")
        written[lang] = pages
    return written

# python-lipas2tak-tool

Fetches outdoor recreation sites and routes in Finland from [Lipas](https://lipas.fi) (supplemented with OpenStreetMap) and turns them into files for TAK clients (ATAK, WinTAK, iTAK). Tested with ATAK 5.8 and TAK Aware; WinTAK and iTAK have not been tested yet. Output is produced per national park, wilderness area, state hiking area and region (maakunta), in Finnish and in English.

| Output | Use |
|---|---|
| Data package `*.zip` (CoT markers + routes) | ATAK/WinTAK without a server, or as a source for a Data Sync feeder |
| `*.kmz` (all features, one folder per type) | import, or target of a KML network link |
| `*_<group>.kmz` | per-group layers (shelters, campfire sites, towers …) |
| `*.kml` (NetworkLink) | auto-refreshing link to the area's KMZ |
| `links/all_<lang>.kml`, `links/<category>_<lang>.kml` | one network link file covering all areas, a folder per category |
| `links/reitit_<lang>.kml` ("All routes") | nationwide route layers, one KMZ per route type (walking, hiking, cycling, snowmobiling …); a type with subtypes is a folder with one layer per subtype (e.g. Snowmobiling → official routes / trails) |
| `*_link.zip` (per area and next to each `links/*.kml`) | package that adds the network link to ATAK as an auto-refreshing layer when opened (QR code / button) |
| `*_gpx.zip` (`<rte>`) | routes that ATAK converts into navigable routes |
| `iconset/lipas2tak_iconset.zip` | icon set, installed once |
| `share/<lang>/*.html` | share pages: QR codes and "open in ATAK" links, one page per category and language |
| `index.json` / `index.html` | catalogue of outputs for feeders and people |
| `status.json` | time of the last check and the next scheduled one (shown on the pages) |

Routes are navigable ATAK routes (`b-m-r`); rest stops along a route are named waypoints. A loop route has one start point ("lähtö ja paluu"). Unnamed path networks (a Lipas site with many connected pieces and no route names, e.g. Isojärvi) are drawn as lines (`u-d-f`) without start/end points; each section is named "<site> · 4,6 km" and its remarks give the network's total length. Marker `remarks` contain a description, services and hashtags (`#laavu #nuuksio #uusimaa`) that can be used to filter the view in ATAK. Route remarks contain length, trail marking, accessibility and a description.

The generated content (remarks, hashtags, folder and file names such as `kansallispuistot/nuuksio`) is in Finnish, with English remarks in the `en` outputs.

Scheduling, file distribution (nginx) and TAK Server feeders live in [docker-lipas-integration](https://github.com/Street3r/docker-lipas-integration).

## Usage

```bash
pip install -e .
lipas2tak run                      # fetch everything and write data/output/
lipas2tak run --only nuuksio       # a single area (slug or key, e.g. kansallispuistot/nuuksio)
lipas2tak fetch --dump data/raw    # save the raw data
lipas2tak build --raw data/raw     # build from saved raw data without network access
lipas2tak schedule --at "mon 04:00"  # container mode: weekly at a fixed time (--tz, default Europe/Helsinki)
lipas2tak publish --raw data/raw --repo <git url> --base-url <public url>   # public build to a git branch
```

Docker:

```bash
docker build -t lipas2tak .
docker run --rm -v "$PWD/data:/data" -e LIPAS2TAK_PUBLIC_BASE_URL=https://example.org/lipas2tak lipas2tak run
```

Prebuilt image: `ghcr.io/street3r/python-lipas2tak-tool` (tags `main`, versions such as `0.1.0`, and `sha-<commit>`), built by CI from this repository.

Tests: `python -m unittest discover -s tests`

Scheduling: with `--at` (env `LIPAS2TAK_SCHEDULE_AT`; time zone `--tz` / `LIPAS2TAK_TZ`) the run happens weekly at that local time. On start it runs at once only if the previous scheduled run was missed (or with `--run-now`), so restarts and updates do not move the schedule. Without `--at`, `--every-days N` runs at start and then every N days.

Coverage check: `python -m lipas2tak.coverage data/raw eramaat` lists the raw Lipas sites, LOIs and OSM elements inside each area of the given categories (or single areas, e.g. `kansallispuistot/petkeljarvi`) that are not in the area's package, with the reason (duplicate, test data, route layer only, route mostly outside the area).

Quality checks: every build lists areas without features, area names missing from `config/area_names.yaml` and files over `quality.max_file_mb` in the log and in `status.json` (`warnings`); the data repository's Stale data workflow opens an issue for them.

### Configuration

- `config/config.yaml`: sources, areas, outputs, public URL. Environment overrides: `LIPAS2TAK_PUBLIC_BASE_URL`, `LIPAS2TAK_OUTPUT_DIR`, `LIPAS2TAK_CACHE_DIR`, `LIPAS2TAK_ICONS_DIR`, `LIPAS2TAK_OVERPASS_URL`, `LIPAS2TAK_CONFIG`, `LIPAS2TAK_TYPES`.
- `config/types.yaml`: feature kinds (Lipas type codes, LOI types, OSM tags), icons, colours and hashtags. Adding a kind needs no code changes.
- `config/area_names.yaml`: base-form area names (e.g. "Nuuksion" → "Nuuksio"). An area category's `name_en` (e.g. `"{name} Wilderness Area"`) gives English names when Lipas has none; `name_en_overrides` sets official names that do not follow the pattern (e.g. Saaristomeri → Archipelago National Park).
- Icons: see [icons/README.md](icons/README.md).

### Output layout

```
data/output/
  index.json, index.html
  links/all_<lang>.kml              network links to all areas
  links/<category>_<lang>.kml       kansallispuistot, eramaat, valtion_retkeilyalueet, maakunnat
  links/reitit_<lang>.kml           network links to the route type layers
  iconset/lipas2tak_iconset.zip
  share/fi|en/index.html, <category>.html   QR codes
  fi|en/<category>/<slug>/
    <slug>_<lang>.zip               data package
    <slug>_<lang>.kmz / .kml         all features + network link
    <slug>_<lang>_<group>.kmz/.kml
    <slug>_<lang>_gpx.zip
  fi|en/reitit/<type>/              nationwide layer per route type or subtype (config.yaml route_types)
    <type>_<lang>.kmz / .kml / _link.zip
```

The route type layers are KMZ only (no data packages or GPX for the whole country). Kinds with `area_packages: false` in `types.yaml` (snowmobile routes and trails, outdoor routes 4403) are only in these layers, not in the area and region packages.

Files are written to a staging directory and swapped in at once, so features removed from the sources disappear automatically. Changes since the previous run are logged in `data/cache/changes.jsonl`.

### KML network links in ATAK

The easiest way is the `_link.zip` package (QR code or button on the share pages): ATAK imports it and adds the refreshing link itself. It is a mission package with one `b-i-r-r` CoT event holding a `<RemoteResource>` – the same thing ATAK produces when a Network Resource is sent to another device (tested with ATAK 5.x). By hand, ATAK (4.2.1+) adds network links via **Import → KML Link**: give a name, paste the URL and enable auto refresh with an interval in seconds. The link is listed in Overlay Manager → Network Resources; nested links (the areas in `links/all_<lang>.kml`) appear as child links that can be switched on and off and whose intervals can be changed.

- One URL for everything: `<base url>/links/all_fi.kml` (national parks, wilderness areas and state hiking areas on, regions off by default).
- All routes by type: `<base url>/links/reitit_fi.kml` (each route type is a child link).
- A single area: `<base url>/fi/kansallispuistot/nuuksio/nuuksio_fi.kmz`.
- WinTAK and Google Earth: open the `.kml` file.

The URLs must stay stable, so the files are served from your own web server (nginx in docker-lipas-integration) or GitHub Pages (`lipas2tak publish`). Dropbox or Google Drive share links, often used for this in TAK tutorials, work for single hand-uploaded files, but every file gets its own unpredictable link, so they don't suit a generated set of ~120 KMZ files referencing each other.

### Share pages and QR codes

`share/<lang>/` has a start page (icon set, all-areas network links) and one page per category with a QR code and an "open in ATAK" button for each area's data package. For refreshing layers the QR code and button import the `_link.zip` package (importing the `.kml` itself would only make a one-off copy); the `.kml` file and a copy-URL button are shown below for other apps and for adding by hand. They use ATAK's import URI `tak://com.atakmap.app/import?url=<percent-encoded URL>`; ATAK asks before importing. iTAK and WinTAK use the plain download links. QR codes need `segno` (installed with the package).

### Publishing

`lipas2tak publish` builds a public version from saved raw data (always the default icon set, public base URL, no per-group KMZ files) and force-pushes it as a single commit to a git branch, e.g. one served by GitHub Pages. Outputs are deterministic (fixed zip timestamps; CoT times record when an item's content last changed), so unchanged files stay byte-identical. When no data changed, only the check time (`status.json`, index files) is updated and no changelog entry is added. If a large push is cut off, files are uploaded in batches to a temporary branch first. A build with more than 10 % fewer features than the published version is not published (a source probably returned incomplete data): the published data is kept, `status.json` gets a `publish_blocked` entry, and `--allow-shrink` publishes it anyway (limit: `PUBLISH_MAX_SHRINK`). Incomplete Overpass answers (an error remark, or less than half of the previous result) are rejected and the previous result is used.

Data package UIDs change whenever the package content changes (uuid5 of area key + content hash), because TAK clients skip a package UID they have already imported. Unchanged content keeps its UID, so re-imports are skipped. With `--watch <index.json>` it publishes after every generator run. See docker-lipas-integration for the container setup.

More details: [docs/design.md](docs/design.md).

## Data sources and licences

| Source | Data | Licence |
|---|---|---|
| [Lipas](https://lipas.fi) REST API v2 `/sports-sites` – University of Jyväskylä | shelters, huts, campfire sites, towers, camping, information points, routes, national park boundaries | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| Lipas `/lois` | toilets, woodsheds, wells, viewpoints, landing spots etc. | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) (Overpass API) | supplementary shelters, fire pits, towers and toilets near outdoor sites | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), © OpenStreetMap contributors |
| [Statistics Finland](https://stat.fi) WFS | region boundaries (used for grouping only) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |

## Licence

- **Code** and the default icon set: [MIT](LICENSE).
- **Generated data**: [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), because it contains OpenStreetMap data. Attribution: *Lipas – University of Jyväskylä (CC BY 4.0); © OpenStreetMap contributors (ODbL 1.0); Statistics Finland (CC BY 4.0)*. Every generated file carries this notice. See [LICENSE-DATA.md](LICENSE-DATA.md).

The data is provided as is; always check current information from the site operator before relying on it in the field.

## Known limitations

- Many sites and main trails maintained by Metsähallitus are missing from Lipas (e.g. in Nuuksio). OpenStreetMap fills some of the gaps.
- Wilderness areas (Lipas 110) and state hiking areas (Lipas 109) use the boundaries in Lipas; the boundaries themselves are not drawn on the map.
- Lipas has no off-road vehicle routes. Snowmobile routes come from Lipas: official routes (4421) and unofficial trails (4422), as separate layers.

---

## Suomeksi lyhyesti

Työkalu hakee retkeilykohteet ja reitit Lipaksesta (sekä täydentävästi OpenStreetMapista) ja tekee niistä TAK-käyttöön datapaketit, KMZ-tiedostot, KML-verkkolinkit ja GPX-reitit kansallispuistoittain, erämaa-alueittain, valtion retkeilyalueittain ja maakunnittain, suomeksi ja englanniksi. Merkkien remarks-kentässä on kuvaus, palvelut ja hashtagit suodatusta varten. Koodi on MIT-lisensoitu, ja tuotettu aineisto on ODbL 1.0 -lisensoitu lähdemainintoineen (Lipas / Jyväskylän yliopisto, © OpenStreetMapin tekijät, Tilastokeskus).

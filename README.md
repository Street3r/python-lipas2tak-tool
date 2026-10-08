# python-lipas2tak-tool

Fetches outdoor recreation sites and routes in Finland from [Lipas](https://lipas.fi) (supplemented with OpenStreetMap) and turns them into files for TAK clients (ATAK, WinTAK, iTAK). Output is produced per national park and per region (maakunta), in Finnish and in English.

| Output | Use |
|---|---|
| Data package `*.zip` (CoT markers + routes) | ATAK/WinTAK without a server, or as a source for a Data Sync feeder |
| `*.kmz` (all features, one folder per type) | import, or target of a KML network link |
| `*_<group>.kmz` | per-group layers (shelters, campfire sites, towers …) |
| `*.kml` (NetworkLink) | auto-refreshing link to the area's KMZ |
| `lipas2tak_<lang>.kml`, `<category>_<lang>.kml` | one network link file covering all areas, a folder per category |
| `*_gpx.zip` (`<rte>`) | routes that ATAK converts into navigable routes |
| `iconset/lipas2tak_iconset.zip` | icon set, installed once |
| `index.json` / `index.html` | catalogue of outputs for feeders and people |

Routes are navigable ATAK routes (`b-m-r`); rest stops along a route are named waypoints. Marker `remarks` contain a description, services and hashtags (`#laavu #nuuksio #uusimaa`) that can be used to filter the view in ATAK. Route remarks contain length, trail marking, accessibility and a description.

The generated content (remarks, hashtags, folder and file names such as `kansallispuistot/nuuksio`) is in Finnish, with English remarks in the `en` outputs.

Scheduling, file distribution (nginx) and TAK Server feeders live in [docker-lipas-integration](https://github.com/Street3r/docker-lipas-integration).

## Usage

```bash
pip install -e .
lipas2tak run                      # fetch everything and write data/output/
lipas2tak run --only nuuksio       # a single area (slug or key, e.g. kansallispuistot/nuuksio)
lipas2tak fetch --dump data/raw    # save the raw data
lipas2tak build --raw data/raw     # build from saved raw data without network access
lipas2tak schedule --every-days 7  # container mode: run now and then weekly
```

Docker:

```bash
docker build -t lipas2tak .
docker run --rm -v "$PWD/data:/data" -e LIPAS2TAK_PUBLIC_BASE_URL=https://example.org/lipas2tak lipas2tak run
```

Tests: `python -m unittest discover -s tests`

### Configuration

- `config/config.yaml`: sources, areas, outputs, public URL. Environment overrides: `LIPAS2TAK_PUBLIC_BASE_URL`, `LIPAS2TAK_OUTPUT_DIR`, `LIPAS2TAK_CACHE_DIR`, `LIPAS2TAK_ICONS_DIR`, `LIPAS2TAK_OVERPASS_URL`, `LIPAS2TAK_CONFIG`, `LIPAS2TAK_TYPES`.
- `config/types.yaml`: feature kinds (Lipas type codes, LOI types, OSM tags), icons, colours and hashtags. Adding a kind needs no code changes.
- `config/area_names.yaml`: base-form area names (e.g. "Nuuksion" → "Nuuksio").
- Icons: see [icons/README.md](icons/README.md).

### Output layout

```
data/output/
  index.json, index.html
  lipas2tak_<lang>.kml              network links to all areas
  kansallispuistot_<lang>.kml, maakunnat_<lang>.kml
  iconset/lipas2tak_iconset.zip
  fi|en/kansallispuistot|maakunnat/<slug>/
    <slug>_<lang>.zip               data package
    <slug>_<lang>.kmz / .kml         all features + network link
    <slug>_<lang>_<group>.kmz/.kml
    <slug>_<lang>_gpx.zip
```

Files are written to a staging directory and swapped in at once, so features removed from the sources disappear automatically. Changes since the previous run are logged in `data/cache/changes.jsonl`.

### KML network links in ATAK

ATAK (4.2.1+) adds network links via **Import → KML Link**: give a name, paste the URL and enable auto refresh with an interval in seconds. The link is listed in Overlay Manager → Network Resources; nested links (the areas in `lipas2tak_<lang>.kml`) appear as child links that can be switched on and off and whose intervals can be changed.

- One URL for everything: `<base url>/lipas2tak_fi.kml` (national parks on, regions off by default).
- A single area: `<base url>/fi/kansallispuistot/nuuksio/nuuksio_fi.kmz`.
- WinTAK and Google Earth: open the `.kml` file.

The URLs must stay stable, so the files are served from your own web server (nginx in docker-lipas-integration). Dropbox or Google Drive share links, often used for this in TAK tutorials, work for single hand-uploaded files, but every file gets its own unpredictable link, so they don't suit a generated set of ~120 KMZ files referencing each other.

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
- Wilderness areas and state hiking areas are not enabled yet.

---

## Suomeksi lyhyesti

Työkalu hakee retkeilykohteet ja reitit Lipaksesta (sekä täydentävästi OpenStreetMapista) ja tekee niistä TAK-käyttöön datapaketit, KMZ-tiedostot, KML-verkkolinkit ja GPX-reitit kansallispuistoittain ja maakunnittain, suomeksi ja englanniksi. Merkkien remarks-kentässä on kuvaus, palvelut ja hashtagit suodatusta varten. Koodi on MIT-lisensoitu, ja tuotettu aineisto on ODbL 1.0 -lisensoitu lähdemainintoineen (Lipas / Jyväskylän yliopisto, © OpenStreetMapin tekijät, Tilastokeskus).

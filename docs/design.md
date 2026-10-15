# Design and decisions

## Architecture

```
Lipas API ───────┐
OpenStreetMap ───┼─> python-lipas2tak-tool ──> data/output/ (index.json + files)
Statistics Fin. ─┘        (generator)                 │
                                                      ├─> nginx: KMZ/KML/data packages over HTTPS
                                                      └─> feeder(s): Data Sync missions on TAK Server
                                                          (one container per server/group/certificate)
```

- **python-lipas2tak-tool** (this repo): fetching, processing and writing files. Knows nothing about TAK Servers.
- **docker-lipas-integration**: the Compose stack (generator + nginx + feeders).
- **Feeders**: read `index.json` and push selected areas and languages into Data Sync missions with their own certificate. The same data can be shared to several servers and groups.

## Processing pipeline

1. **Fetch** (`fetch_raw`): Lipas sports sites by type code, Lipas LOIs (locations of interest), OSM Overpass queries per feature kind, national park boundaries (Lipas type 111) and regions (Statistics Finland WFS). Responses are cached on disk.
2. **Normalise** (`normalize.py`): each source item is classified into a *kind* from `config/types.yaml` (icon, CoT type, colour, hashtags, group). Test data is filtered by name and status. Routes are simplified (Douglas–Peucker, 5 m) and route pieces are merged (5 m snap). At junctions, pieces continue along the straightest branch (turn ≤ `routes.junction_max_turn_deg`, 60°), so a path network becomes a few long lines instead of many short ones (`geo.merge_strokes`; Isojärvi: 23 pieces → 11 lines). The same pairing bridges small gaps, so a path drawn as short dashes becomes one line, and short pieces lying on top of a longer line are dropped (`geo.drop_covered`). Over all of Lipas, multi-piece routes go from 9375 to 4786 lines. Long routes are split at region borders (`areas.split_routes_by_region`, sections of at least 5 km, UIDs `<uid>-m<n>`), so e.g. EuroVelo 11 appears in each region it passes through instead of only one. Multi-part routes become separate features that share a `group_uid`. A Lipas site without named sub-routes whose pieces meet at junctions is a *path network* (`Feature.network_km`): its sections are drawn lines with the section length in the name, not navigable routes with start/end points per piece.
3. **OSM supplement**: an element that matches several kinds becomes one feature under the main kind (tupa > kota > laavu > keittokatos > näkötorni > telttapaikka > nuotiopaikka > näköalapaikka > käymälä > vesipiste); the other kind is added as a service, e.g. a lean-to tagged as a fire pit is a *laavu* with "Services: fire place" (`normalize.merge_osm_kinds`); its hashtag is added too (`#nuotiopaikka`). OSM features are kept if they are near Lipas features or routes, or inside a protected area (archipelago parks such as Linnansaari have almost nothing in Lipas). Then OSM features are kept only if they are within the kind's context radius of other outdoor features or routes, and dropped if Lipas already has a feature of the same group nearby (dedupe radius).
4. **Waypoints** (`waypoints.py`): rest stops (shelters, fire places, camping, towers) within 75 m of a route become named waypoints. Features less than 200 m apart form one cluster with a single waypoint; the representative is picked by group priority.
5. **Areas** (`areas.py`): a point belongs to a park if it is inside the boundary plus a 500 m buffer. A route part belongs to a park if ≥ 30 % of its length or ≥ 3 km lies inside. Regions are assigned by a majority vote of sample points along a route (fallback: nearest within 20 km).
6. **Write** (`pipeline.py`, `writers/`): per area and language, a data package, KMZ (all + per group), KML network links and a GPX archive; plus the iconset and `index.json`/`index.html`. Output is built in a staging directory and swapped in atomically. Changes compared with the previous run are logged to `data/cache/changes.jsonl`.

## Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Feature types | lean-tos, huts (kota, kammi, tupa), campfire and cooking sites, observation towers and viewpoints, camping sites, toilets, information points, nature centres, woodsheds, water points, landing spots, parking; routes: nature trails, hiking routes, multi-use, cycling and paddling routes. **No winter routes.** |
| 2 | Toilets and missing rest stops | Lipas LOI API (dry-toilet, wc) + OpenStreetMap near outdoor sites |
| 3 | Areas | national parks → wilderness areas → state hiking areas (the last two not yet enabled) |
| 4 | Regions | all maintainers, but only the types in #1 (no fitness trails etc.) |
| 5 | Splitting | one package per area; KMZ also per group; hashtags in remarks |
| 6 | Icons | own pictogram set by default; a custom set can be configured (`LIPAS2TAK_ICONS_DIR`) |
| 7 | Route colours | similar routes share a colour (types.yaml) |
| 8 | Route format | navigable ATAK routes (`b-m-r`) by default, drawn lines (`u-d-f`) optional; GPX `<rte>` |
| 9 | Languages | Finnish and English as separate outputs |
| 10 | Remarks | services + short description ≤ 500 characters + link + hashtags |
| 11 | TAK Server | 5.8; Data Sync per group/channel |
| 12 | Clients | ATAK 5.8 and WinTAK 5.8 first |
| 13 | Distribution | public HTTPS on own domain |
| 14 | Deletions | features removed at the source are removed from the output; weekly change log |
| 15 | Elevation | not written; ATAK uses its own elevation model |
| 16 | Licence | code MIT; generated data ODbL 1.0 with source attribution ([LICENSE-DATA.md](../LICENSE-DATA.md)) |

## CoT formats (from an ATAK-exported reference package)

- Mission Package v2: `MANIFEST/manifest.xml` and `<uid>/<uid>.cot`. `onReceiveDelete=false` (tested in ATAK): the package stays in the Data Packages list after import, so its contents can be hidden or removed together.
- Package UID = uuid5(area key + content hash). TAK clients skip a package UID they have already imported, so the UID changes whenever the content changes and stays the same otherwise (no needless re-imports). The package name carries the date of the newest change, e.g. `Nuuksion kansallispuisto (fi) 2026-10-21`. CoT items keep stable UIDs (`lipas-<id>`, `osm-<id>` …), so a new version updates existing markers instead of duplicating them. Items removed at the source are not removed from devices by a new package; delete the old package (with its contents) before importing the new one, or use Data Sync.
- Marker: `a-u-G` with `usericon iconsetpath="<iconset uid>/Retkeily/<icon>.png"`.
- Route `b-m-r`: `point` 0,0, points as `<link>` elements (`b-m-p-w` at the start, end and named waypoints, `b-m-p-c` in between, relation `c`), `link_attr` (Walking / On Foot / prefix CP / Ascending Check Points), empty `__routeinfo/__navcues`.
- A 10.6 km reference route had 421 points without simplification, so routes with hundreds of points work.
- Colour is a signed ARGB integer (`-8454017` = `#7F007F`).
- Drawn line `u-d-f` needs `fillColor 0`, otherwise closed loops are filled.
- `remarks` is free text; hashtags are written into it as is.
- Iconset zip: `iconset.xml` with camelCase attributes (`defaultGroup`, `skipResize`); the group is the directory in the zip.

## KML network links

- ATAK: Import → *KML Link* (URL + auto refresh interval). Since ATAK 4.2.1 nested network links are shown as child links in Overlay Manager and their intervals can be changed; 4.3 improved nested link handling.
- Generated: a network link `.kml` per area (to its KMZ), and per language `links/all_<lang>.kml` plus `links/<category>_<lang>.kml` with a folder per category. Regions are `visibility 0` by default (`outputs.root_links_visible`).
- Per-group network links are off by default (`outputs.network_link_per_group`): the KMZ already has a folder per group, and ~1,000 link files were too many to navigate. Per-group KMZ files are still written.
- Refresh interval 86,400 s; the data changes weekly.
- Tested (ATAK 5.8): importing a network-link `.kml` via `tak://…/import` or a QR code creates a one-off copy, not a refreshing link. A refreshing link is created by importing a *Remote Resource* package instead (`writers/remote_resource.py`, `<area>_<lang>_link.zip` and `links/*_link.zip`): a mission package with one `b-i-r-r` CoT event and `<RemoteResources><RemoteResource name url type refreshSeconds deleteOnExit/>`, the same as ATAK's own export of a Network Resource (verified with an exported package from ATAK). The share pages import that package; the `.kml` URL is still offered for copying.
- Tested (ATAK 5.8): ATAK fetches only the child links that are switched on; children with `visibility 0` are not fetched until switched on. The whole link or single areas can be switched on. A park switched on both on its own and through its region shows its features twice at the same positions (harmless, documented). Auto refresh works. Not tested yet: WinTAK, iTAK.

## Data notes (Lipas, October 2026)

- National parks are Lipas type 111 (41 parks). Nuuksio = Lipas id 606198.
- Many sites and main trails maintained by Metsähallitus are missing from Lipas (e.g. most lean-tos and the main trails in Nuuksio). OpenStreetMap is used to fill gaps for shelters, fire places, towers and toilets.
- The LOI API contains toilets (`dry-toilet` ≈ 180 nationwide) and some test data (filtered by name and status).
- Type code 205 is not in use; landing spots come from LOIs (`landing-spot`).
- The type code / source for state hiking areas is still to be determined.
- Full run (October 2026): about 8,500 Lipas sites, 1,050 LOIs and ~17,000 OSM elements → ~25,500 features in 58 areas (41 parks, 19 regions; Linnansaari and Perämeri currently have no features). Lipas fetch ~1 min; OSM fetch 1–15 min depending on how busy Overpass is; processing ~4 min.
- Public Overpass servers often answer 504/429: retries with longer waits, fallback servers and the previous cached result are used (`sources.osm.overpass_fallback_urls`).

## ATAK test checklist

1. ✅ Iconset (`defaultGroup`/`skipResize`, `Retkeily/*.png`) works in ATAK 5.8.
2. ✅ `u-d-f` lines without elevation work; loops need `fillColor 0`.
3. ✅ Hashtag search works even when tags are at the end of long remarks.
4. ✅ KML Link with `links/all_fi.kml` and `all_en.kml`, category links and single-area KMZ: child links, visibility, refresh.
5. `b-m-r` routes with named waypoints: navigation and checkpoint names.
6. GPX `<rte>` → ATAK route; whether `<desc>` ends up in remarks.
7. KMZ network link refresh: ✅ ATAK, ✅ TAK Aware; WinTAK and iTAK not tested yet.
8. ✅ Data package update: a new version (new UID) updates the existing items without duplicates; same content is skipped. The old package stays in Data Packages (delete by hand; the name carries the date). Importing the other language switches the texts.
9. ✅ A new icon set version updates markers already on the map.
10. Weekly run: the layer refreshes after the next scheduled publication without a re-import.

## Next steps

1. Remaining tests per the checklist above (5, 6, 10; WinTAK and iTAK later).
2. Data Sync feeder in docker-lipas-integration.
3. Wilderness areas and state hiking areas.

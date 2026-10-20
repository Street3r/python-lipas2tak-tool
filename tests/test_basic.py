"""Tests: python -m unittest discover -s tests  (also works with pytest)."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from lipas2tak import geo, pipeline, remarks
from lipas2tak.config import load_settings, slugify
from lipas2tak.writers import cot

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "nuuksio"


class GeoTests(unittest.TestCase):
    def test_simplify_keeps_ends_and_reduces(self):
        line = [(24.5 + i * 0.0001, 60.3 + (0.00001 if i % 2 else 0)) for i in range(100)]
        s = geo.simplify(line, 5.0)
        self.assertEqual(s[0], line[0])
        self.assertEqual(s[-1], line[-1])
        self.assertLess(len(s), 10)

    def test_merge_lines_joins_pieces(self):
        a = [(24.0, 60.0), (24.01, 60.0)]
        b = [(24.02, 60.0), (24.01, 60.0)]  # opposite direction
        merged = geo.merge_lines([a, b])
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]), 3)

    def test_merge_lines_keeps_branches(self):
        center = (24.0, 60.0)
        lines = [[center, (24.01, 60.0)], [center, (23.99, 60.0)], [center, (24.0, 60.01)]]
        self.assertEqual(len(geo.merge_lines(lines)), 3)

    def test_merge_lines_many_pieces_fast(self):
        import random, time
        pts = [(24.0 + i * 0.001, 60.0) for i in range(3001)]
        pieces = [[pts[i], pts[i + 1]] for i in range(3000)]
        random.Random(1).shuffle(pieces)
        pieces = [p if i % 2 else p[::-1] for i, p in enumerate(pieces)]
        t = time.time()
        merged = geo.merge_lines(pieces)
        self.assertLess(time.time() - t, 2.0)
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]), 3001)

    def test_waypoint_clusters(self):
        from lipas2tak import waypoints
        from lipas2tak.model import Feature, Localized
        line = [(24.50, 60.30), (24.52, 60.30), (24.54, 60.30)]
        route = Feature(uid="r", source="t", source_id="r", kind="luontopolku", name=Localized("R"), lines=[line])
        def pt(uid, kind, lon):
            return Feature(uid=uid, source="t", source_id=uid, kind=kind, name=Localized(uid), point=(lon, 60.3002))
        feats = [route, pt("nuotio", "nuotiopaikka", 24.5100), pt("laavu", "laavu", 24.5105),
                 pt("teltta", "telttapaikka", 24.5110), pt("torni", "nakotorni", 24.5300)]
        kg = {"luontopolku": "reitit", "nuotiopaikka": "tulentekopaikat", "laavu": "suojat",
              "telttapaikka": "telttailu", "nakotorni": "nakotornit"}
        waypoints.attach_waypoints(feats, kg, ["suojat", "tulentekopaikat", "telttailu", "nakotornit"],
                                   radius_m=75, cluster_m=200)
        self.assertEqual(len(route.waypoints), 2)                   # cluster + tower
        self.assertEqual(route.waypoints[0][1][0].uid, "laavu")     # the shelter represents the cluster
        self.assertEqual({f.uid for f in route.waypoints[0][1]}, {"laavu", "nuotio", "teltta"})

    def test_control_characters_removed_from_xml(self):
        # Lipas descriptions can contain e.g. U+0002; one such character breaks the whole KML
        xml = cot.marker("u1", "a-u-G", 60.0, 24.0, "Kuru\x02", "Etelä-Suo\x02men louhikko", None)
        root = ET.fromstring(xml)
        self.assertEqual(root.find("detail/remarks").text, "Etelä-Suomen louhikko")
        self.assertEqual(root.find("detail/contact").get("callsign"), "Kuru")

    def test_dashed_line_and_duplicates(self):
        # A path drawn as 4 m dashes with 3 m gaps becomes one line
        dashes, lon = [], 24.5
        for _ in range(30):
            dashes.append([(lon, 60.3), (lon + 0.00007, 60.3)])
            lon += 0.00012
        self.assertEqual(len(geo.merge_strokes(dashes, 5, 60)), 1)
        # A short piece on top of a longer line is dropped
        long_line = [(24.5, 60.3), (24.51, 60.3)]
        dup = [(24.5050, 60.30001), (24.5052, 60.30001)]
        self.assertEqual(geo.drop_covered([long_line, dup]), [long_line])

    def test_long_route_split_by_region(self):
        from lipas2tak import areas as areas_mod
        from lipas2tak.model import AreaDef, Feature, Localized
        def box(x0, x1):
            return {"type": "Polygon", "coordinates": [[[x0, 60], [x1, 60], [x1, 61], [x0, 61], [x0, 60]]]}
        regs = [AreaDef("a", "maakunnat", Localized("A"), "a", box(24, 25)),
                AreaDef("b", "maakunnat", Localized("B"), "b", box(25, 26))]
        line = [(24.1 + i * 0.02, 60.5) for i in range(85)]          # 24.1 .. 25.78
        f = Feature(uid="lipas-9", source="lipas", source_id="9", kind="retkeilyreitti",
                    name=Localized("Pitkä reitti"), lines=[line])
        out = areas_mod.split_routes_by_region([f], regs)
        self.assertEqual([g.uid for g in out], ["lipas-9-m1", "lipas-9-m2"])
        self.assertTrue(all(g.group_uid == "lipas-9" for g in out))
        self.assertEqual(out[0].lines[0][-1], out[1].lines[0][0])  # sections connect
        areas_mod.assign_regions(out, regs)
        self.assertEqual([g.region for g in out], ["maakunnat/a", "maakunnat/b"])

    def test_merge_strokes_through_junction(self):
        # A cross: four arms meeting at one point become two straight lines
        c = (24.5, 60.3)
        arms = [[c, (24.51, 60.3)], [c, (24.49, 60.3)], [c, (24.5, 60.305)], [c, (24.5, 60.295)]]
        self.assertEqual(len(geo.merge_lines(arms)), 4)
        strokes = geo.merge_strokes(arms)
        self.assertEqual(len(strokes), 2)
        self.assertTrue(geo.has_junction(arms))
        self.assertFalse(geo.has_junction(arms[:2]))
        # A sharp turn is not joined
        self.assertEqual(len(geo.merge_strokes([[c, (24.51, 60.3)], [c, (24.51, 60.3005)], [c, (24.49, 60.3)]], 5, 60)), 2)

    def test_path_network_sections(self):
        from lipas2tak import normalize
        settings = load_settings()
        clf = normalize.Classifier(settings)
        c = [24.5, 60.3]
        def ln(a, b, fid):
            return {"type": "Feature", "id": fid, "geometry": {"type": "LineString", "coordinates": [a, b]}}
        site = {"lipas-id": 1, "type": {"type-code": 4405}, "name": "Esimerkkipuiston reitit", "status": "active",
                "properties": {"route-length-km": 9}, "location": {"geometries": {"features": [
                    ln(c, [24.51, 60.3], "a"), ln(c, [24.49, 60.3], "b"), ln(c, [24.5, 60.305], "c")]}}}
        feats = normalize.lipas_site_to_features(site, clf, settings)
        self.assertEqual(len(feats), 2)
        self.assertTrue(all(f.network_km and f.group_uid == "lipas-1" for f in feats))
        kind = settings.kinds[feats[0].kind]
        name = remarks.display_name(feats[0], kind, "fi")
        self.assertTrue(name.startswith("Esimerkkipuiston reitit · ") and name.endswith(" km"))
        self.assertIn("Reitistö yhteensä", remarks.remarks(feats[0], kind, "fi", {}, settings))

    def test_merge_lines_loop(self):
        a = [(24.0, 60.0), (24.01, 60.0), (24.01, 60.01)]
        b = [(24.01, 60.01), (24.0, 60.01), (24.0, 60.0)]
        merged = geo.merge_lines([a, b])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0][0], merged[0][-1])

    def test_area_buffer(self):
        sq = {"type": "Polygon", "coordinates": [[[24, 60], [25, 60], [25, 61], [24, 61], [24, 60]]]}
        a = geo.Area(sq)
        self.assertTrue(a.within((24.5, 60.5)))
        outside = (25.005, 60.5)  # ~280 m east
        self.assertFalse(a.within(outside))
        self.assertTrue(a.within(outside, buffer_m=500))


class FormatTests(unittest.TestCase):
    def test_argb_matches_atak_example(self):
        # colour of the ATAK example route -8454017 = 0xFF7F007F
        self.assertEqual(cot.argb_int("#7F007F"), -8454017)
        self.assertEqual(cot.argb_int("#FFFFFF"), -1)

    def test_slugify_ascii(self):
        self.assertEqual(slugify("Näkötorni"), "nakotorni")
        self.assertEqual(slugify("Pallas-Yllästunturi"), "pallasyllastunturi")

    def test_route_structure_matches_atak_example(self):
        xml = cot.route("r1", [(24.5, 60.3), (24.51, 60.31), (24.52, 60.3)], "Reitti", "rem #x",
                        "#7F007F", "Reitti – alku", "Reitti – loppu")
        root = ET.fromstring(xml)
        self.assertEqual(root.get("type"), "b-m-r")
        self.assertEqual(root.find("point").get("lat"), "0.0")
        links = root.findall("detail/link")
        self.assertEqual([l.get("type") for l in links], ["b-m-p-w", "b-m-p-c", "b-m-p-w"])
        self.assertEqual(links[0].get("callsign"), "Reitti – alku")
        self.assertEqual(links[0].get("uid"), "r1-p0")
        self.assertEqual(links[1].get("relation"), "c")
        la = root.find("detail/link_attr")
        self.assertEqual(la.get("color"), "-8454017")
        self.assertEqual(la.get("method"), "Walking")
        self.assertEqual(la.get("order"), "Ascending Check Points")
        self.assertIsNotNone(root.find("detail/__routeinfo/__navcues"))
        self.assertEqual(root.find("detail/remarks").text, "rem #x")

    def test_polyline_has_no_altitude(self):
        xml = cot.polyline("u1", [(24.5, 60.3), (24.6, 60.4)], "R", "rem", "#00FF00")
        root = ET.fromstring(xml)
        pts = [l.get("point") for l in root.iter("link")]
        self.assertEqual(pts, ["60.3,24.5", "60.4,24.6"])
        self.assertEqual(root.get("type"), "u-d-f")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["LIPAS2TAK_OUTPUT_DIR"] = str(self.tmp / "out")
        os.environ["LIPAS2TAK_CACHE_DIR"] = str(self.tmp / "cache")
        self.settings = load_settings()
        self.raw = pipeline.RawData.load(FIXTURE)

    def tearDown(self):
        shutil.rmtree(self.tmp)
        for k in ("LIPAS2TAK_OUTPUT_DIR", "LIPAS2TAK_CACHE_DIR"):
            os.environ.pop(k, None)

    def run_once(self):
        return pipeline.run(self.settings, self.raw, now=datetime(2026, 10, 7, tzinfo=timezone.utc))

    def test_end_to_end(self):
        res = self.run_once()
        out = self.tmp / "out"
        idx = json.loads((out / "index.json").read_text())
        keys = {(e["key"], e["lang"]) for e in idx["areas"]}
        self.assertIn(("kansallispuistot/nuuksio", "fi"), keys)
        self.assertIn(("maakunnat/uusimaa", "en"), keys)
        self.assertIn(("maakunnat/kanta-hame", "fi"), keys)  # axis order fixed

        park = next(e for e in idx["areas"] if e["key"] == "kansallispuistot/nuuksio" and e["lang"] == "fi")
        uids = set(park["uids"])
        self.assertIn("lipas-900020", uids)          # Haukankierros merged into one line
        with zipfile.ZipFile(out / park["files"]["datapackage"]) as z:
            r = ET.fromstring(z.read("lipas-900020/lipas-900020.cot"))
        self.assertEqual(r.get("type"), "b-m-r")      # routes as navigable routes
        named = [l.get("callsign") for l in r.findall("detail/link") if l.get("type") == "b-m-p-w"]
        self.assertIn("Kolmoislammen laavu", named)   # rest stop (OSM) along the route as a waypoint
        # A loop has one start point: "lähtö ja paluu" at both ends
        self.assertTrue(named[0].endswith("lähtö ja paluu") and named[-1] == named[0])
        self.assertNotIn("lipas-900008", uids)       # Testilaavu filtered out
        self.assertIn("osm-n1002", uids)             # OSM toilet near an outdoor site
        self.assertNotIn("osm-n1001", uids)          # duplicate of the LOI toilet
        self.assertFalse(any(u.startswith("osm-w2001") for u in uids))  # Helsinki WC excluded
        self.assertEqual(park["counts"]["kota"], 1)
        self.assertIn("osm-n3002", uids)             # OSM lean-to missing from Lipas
        self.assertNotIn("osm-n3001", uids)          # same lean-to as in Lipas
        self.assertNotIn("osm-n3003", uids)          # not near outdoor sites

        # Data package: manifest + CoT parse, hashtags in remarks
        dp = out / park["files"]["datapackage"]
        with zipfile.ZipFile(dp) as z:
            man = ET.fromstring(z.read("MANIFEST/manifest.xml"))
            ev = ET.fromstring(z.read("lipas-900001/lipas-900001.cot"))
            self.assertIn("OpenStreetMap", z.read("ATTRIBUTION.txt").decode())
        self.assertEqual(man.find("Configuration/Parameter[@name='onReceiveDelete']").get("value"), "false")
        att = man.find("Contents/Content[@zipEntry='ATTRIBUTION.txt']")
        self.assertEqual(att.get("ignore"), "true")
        rem = ev.find("detail/remarks").text
        self.assertIn("#laavu", rem)
        self.assertIn("#nuuksio", rem)
        self.assertIn("#uusimaa", rem)
        self.assertIn("WC", rem)
        icon = ev.find("detail/usericon").get("iconsetpath")
        self.assertTrue(icon.endswith("/Retkeily/laavu.png"))

        # KMZ: doc.kml parses and icons are included
        with zipfile.ZipFile(out / park["files"]["kmz"]) as z:
            ET.fromstring(z.read("doc.kml"))
            self.assertIn("files/laavu.png", z.namelist())

        # GPX without elevation
        with zipfile.ZipFile(out / park["files"]["gpx_zip"]) as z:
            g = z.read(next(n for n in z.namelist() if n.endswith(".gpx"))).decode()
            self.assertIn("ATTRIBUTION.txt", z.namelist())
        self.assertNotIn("<ele>", g)
        self.assertIn("<copyright", g)
        ET.fromstring(g)

    def test_share_pages(self):
        self.run_once()
        out = self.tmp / "out"
        idx = json.loads((out / "index.json").read_text())
        self.assertEqual(idx["share"]["fi"][0], "share/fi/index.html")
        page = (out / "share/en/kansallispuistot.html").read_text()
        self.assertIn("Nuuksio", page)
        self.assertIn("tak://com.atakmap.app/import?url=https%3A%2F%2Fexample.org%2Flipas2tak%2Fen%2F"
                      "kansallispuistot%2Fnuuksio%2Fnuuksio_en.zip", page)
        start = (out / "share/fi/index.html").read_text()
        # Refreshing links: tak:// import of a Remote Resource package; the .kml URL can be copied
        self.assertIn("import?url=https%3A%2F%2Fexample.org%2Flipas2tak%2Flinks%2Fall_fi_link.zip", start)
        self.assertNotIn("links%2Fall_fi.kml", start)
        self.assertIn("data-copy='https://example.org/lipas2tak/links/all_fi.kml'", start)
        self.assertIn("nuuksio_en_link.zip", page)
        self.assertIn("../en/index.html", start)       # language switch

    def test_wilderness_and_state_hiking_areas(self):
        self.run_once()
        out = self.tmp / "out"
        idx = json.loads((out / "index.json").read_text())
        wild = next(e for e in idx["areas"] if e["key"] == "eramaat/kasivarsi" and e["lang"] == "fi")
        hike = next(e for e in idx["areas"] if e["key"] == "valtion_retkeilyalueet/ruunaa" and e["lang"] == "en")
        self.assertIn("osm-n3003", wild["uids"])     # OSM lean-to kept: inside a protected area
        self.assertIn("lipas-900009", hike["uids"])
        self.assertEqual(hike["name"], "Ruunaa Hiking Area")   # no English name in Lipas: name_en
        self.assertEqual(wild["name"], "Käsivarren erämaa-alue")
        self.assertTrue((out / "fi/eramaat/kasivarsi/kasivarsi_fi.zip").exists())
        self.assertFalse(any(e["key"] == "eramaat/koiraharju" for e in idx["areas"]))  # exclude_lipas_ids
        self.assertEqual(idx["links"]["fi"]["valtion_retkeilyalueet"], "links/valtion_retkeilyalueet_fi.kml")
        page = (out / "share/fi/eramaat.html").read_text()
        self.assertIn("Käsivarren erämaa-alue", page)
        self.assertIn("#kasivarsi", page)
        nav = page[page.index("<nav>"):page.index("</nav>")]
        order = [nav.index(t) for t in ("Kansallispuistot", "Erämaa-alueet", "Valtion retkeilyalueet", "Maakunnat")]
        self.assertEqual(order, sorted(order))

    def test_quality_warnings(self):
        far = [[[29.0, 69.0], [29.01, 69.0], [29.01, 69.01], [29.0, 69.0]]]
        self.raw.area_sites["eramaat"].append({
            "lipas-id": 999001, "name": "Uudenkylän erämaa-alue",
            "location": {"geometries": {"features": [{"geometry": {"type": "Polygon", "coordinates": far}}]}}})
        self.settings.raw["quality"] = {"max_file_mb": 0.001}
        res = self.run_once()
        w = res["warnings"]
        self.assertIn("eramaat/uudenkyla: base form of 'Uudenkylän erämaa-alue' guessed; "
                      "add it to config/area_names.yaml", w)
        self.assertIn("eramaat/uudenkyla: no features, no package", w)
        self.assertTrue(any(x.startswith("fi/kansallispuistot/nuuksio/") and "MB (limit" in x for x in w))
        self.assertFalse(any(x.startswith("eramaat/kasivarsi") for x in w))   # in area_names.yaml, has features
        status = json.loads((self.tmp / "out" / "status.json").read_text())
        self.assertEqual(status["warnings"], w)

    def test_area_english_names(self):
        from lipas2tak import areas
        sq = [[24.4, 60.2], [24.5, 60.2], [24.5, 60.3], [24.4, 60.2]]
        sites = [{"lipas-id": i, "name": n, "location": {"geometries": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [sq]}}]}}}
            for i, n in enumerate(["Nuuksion kansallispuisto", "Saaristomeren kansallispuisto"])]
        defs = areas.areas_from_lipas_sites(sites, "kansallispuistot", self.settings.get("areas", "kansallispuistot"),
                                            self.settings.area_names.get("kansallispuistot"))
        self.assertEqual([a.name.en for a in defs], ["Nuuksio National Park", "Archipelago National Park"])
        self.assertEqual([a.name.fi for a in defs], ["Nuuksion kansallispuisto", "Saaristomeren kansallispuisto"])

    def test_coverage_report(self):
        from lipas2tak import coverage
        rep = coverage.report(FIXTURE, ["kansallispuistot"])
        self.assertIn("Testilaavu | lipas:900008", rep)
        self.assertIn("area_packages false", rep)
        self.assertIn("Haukkalammen laavu = Haukkalammen laavu (lipas, ", rep)  # duplicate of the Lipas lean-to

    def test_osm_element_in_two_kinds_kept_once(self):
        # Kolmoislammen laavu (kept as laavu) also tagged as a fire pit
        el = next(e for e in self.raw.osm["laavu"] if e["id"] == 3002)
        self.raw.osm["nuotiopaikka"] = [dict(el)]
        self.run_once()
        out = self.tmp / "out"
        idx = json.loads((out / "index.json").read_text())
        for e in idx["areas"]:
            if "datapackage" not in e["files"]:   # route type layers: KMZ only
                continue
            with zipfile.ZipFile(out / e["files"]["datapackage"]) as z:
                names = z.namelist()
            self.assertEqual(len(names), len(set(names)), e["key"])
        park = next(e for e in idx["areas"] if e["key"] == "kansallispuistot/nuuksio" and e["lang"] == "fi")
        with zipfile.ZipFile(out / park["files"]["datapackage"]) as z:
            ev = ET.fromstring(z.read("osm-n3002/osm-n3002.cot"))
        self.assertTrue(ev.find("detail/usericon").get("iconsetpath").endswith("/laavu.png"))
        self.assertIn("tulipaikka", ev.find("detail/remarks").text)
        self.assertIn("#nuotiopaikka", ev.find("detail/remarks").text)

    def test_osm_inside_protected_area_kept_without_lipas_context(self):
        from lipas2tak.model import Feature, Localized
        from lipas2tak.normalize import dedupe_osm
        f = Feature(uid="osm-n9", source="osm", source_id="node/9", kind="laavu", name=Localized(),
                    point=(28.55, 62.05))      # e.g. an island in an archipelago park, nothing in Lipas nearby
        kw = dict(context_radius_m=1500, dedupe_radius_m=120)
        self.assertEqual(dedupe_osm([f], [], **kw), [])
        self.assertEqual(dedupe_osm([f], [], in_area=lambda p: True, **kw), [f])

    def test_merge_osm_kinds_rules(self):
        from lipas2tak.model import Feature, Localized
        from lipas2tak.normalize import merge_osm_kinds

        def f(kind):
            return Feature(uid="osm-n1", source="osm", source_id="node/1", kind=kind, name=Localized(),
                           point=(25.0, 60.0))
        cases = [
            (("nakoalapaikka", "nakotorni"), "nakotorni", []),
            (("nuotiopaikka", "laavu"), "laavu", ["fireplace"]),
            (("kota", "tupa"), "tupa", []),
            (("nuotiopaikka", "keittokatos"), "keittokatos", []),
            (("nuotiopaikka", "kota"), "kota", ["fireplace"]),
            (("nuotiopaikka", "telttapaikka"), "telttapaikka", ["fireplace"]),
            (("nakoalapaikka", "nuotiopaikka"), "nuotiopaikka", ["viewpoint"]),
            (("nakoalapaikka", "laavu"), "laavu", ["viewpoint"]),
            (("kaymala", "telttapaikka"), "telttapaikka", ["toilet"]),
        ]
        for kinds, winner, services in cases:
            res = merge_osm_kinds({k: [f(k)] for k in kinds})
            got = [(k, x.services) for k, xs in res.items() for x in xs]
            self.assertEqual(got, [(winner, services)], kinds)

    def test_output_is_deterministic(self):
        """A second run with unchanged data produces byte-identical files
        (apart from the index files that carry the run time)."""
        out = self.tmp / "out"

        def snapshot():
            return {str(p.relative_to(out)): p.read_bytes() for p in out.rglob("*") if p.is_file()}

        pipeline.run(self.settings, self.raw, now=datetime(2026, 10, 7, tzinfo=timezone.utc))
        first = snapshot()
        pipeline.run(self.settings, self.raw, now=datetime(2026, 10, 14, 5, 30, tzinfo=timezone.utc))
        second = snapshot()
        self.assertEqual(set(first), set(second))
        changed = sorted(k for k in first if first[k] != second[k])
        self.assertEqual(changed, ["index.html", "index.json", "status.json"])

    def test_package_uid_changes_with_content(self):
        """TAK clients skip a package UID they have already imported, so the UID
        must change whenever the content changes, and only then."""
        out = self.tmp / "out"

        def uids():
            idx = json.loads((out / "index.json").read_text())
            res = {}
            for e in idx["areas"]:
                if "datapackage" not in e["files"]:
                    continue
                with zipfile.ZipFile(out / e["files"]["datapackage"]) as z:
                    man = ET.fromstring(z.read("MANIFEST/manifest.xml"))
                uid = man.find("Configuration/Parameter[@name='uid']").get("value")
                self.assertEqual(uid, e["datapackage_uid"])
                res[f"{e['key']}/{e['lang']}"] = uid
            return res

        pipeline.run(self.settings, self.raw, now=datetime(2026, 10, 7, tzinfo=timezone.utc))
        first = uids()
        self.assertEqual(len(set(first.values())), len(first))      # unique per area and language
        pipeline.run(self.settings, self.raw, now=datetime(2026, 10, 14, tzinfo=timezone.utc))
        self.assertEqual(uids(), first)                               # unchanged content -> same UID

        site = next(s for s in self.raw.sites if s.get("lipas-id") == 900001)
        site["name"] = site["name"] + " (uusi)"
        pipeline.run(self.settings, self.raw, now=datetime(2026, 10, 21, tzinfo=timezone.utc))
        third = uids()
        self.assertNotEqual(third["kansallispuistot/nuuksio/fi"], first["kansallispuistot/nuuksio/fi"])
        self.assertNotEqual(third["maakunnat/uusimaa/fi"], first["maakunnat/uusimaa/fi"])
        self.assertEqual(third["maakunnat/kanta-hame/fi"], first["maakunnat/kanta-hame/fi"])
        with zipfile.ZipFile(out / "fi/kansallispuistot/nuuksio/nuuksio_fi.zip") as z:
            name = ET.fromstring(z.read("MANIFEST/manifest.xml")).find(
                "Configuration/Parameter[@name='name']").get("value")
        self.assertTrue(name.endswith("2026-10-21"), name)          # version date of the newest change

    def test_network_link_collections(self):
        self.run_once()
        out = self.tmp / "out"
        idx = json.loads((out / "index.json").read_text())
        self.assertEqual(idx["links"]["fi"]["all"], "links/all_fi.kml")
        self.assertEqual(idx["links"]["en"]["maakunnat"], "links/maakunnat_en.kml")
        ns = {"k": "http://www.opengis.net/kml/2.2"}
        root = ET.parse(out / "links/all_fi.kml").getroot()
        folders = root.findall("k:Document/k:Folder", ns)
        self.assertEqual([f.find("k:name", ns).text for f in folders],
                         ["Kansallispuistot", "Erämaa-alueet", "Valtion retkeilyalueet", "Maakunnat"])
        hrefs = [h.text for h in root.iter("{http://www.opengis.net/kml/2.2}href")]
        self.assertIn("https://example.org/lipas2tak/fi/kansallispuistot/nuuksio/nuuksio_fi.kmz", hrefs)
        # regions are off by default
        self.assertEqual(folders[1].find("k:NetworkLink/k:visibility", ns).text, "1")
        self.assertEqual(folders[3].find("k:NetworkLink/k:visibility", ns).text, "0")
        # per-area link stays, per-group links are off by default
        d = out / "fi/kansallispuistot/nuuksio"
        self.assertTrue((d / "nuuksio_fi.kml").exists())
        self.assertFalse(list(d.glob("nuuksio_fi_*.kml")))
        self.assertTrue(list(d.glob("nuuksio_fi_*.kmz")))
        self.assertIn("links/all_fi.kml", (out / "index.html").read_text())

    def test_route_type_layers(self):
        """Nationwide KMZ layer per route type, collected in links/reitit_<lang>.kml."""
        self.run_once()
        out = self.tmp / "out"
        idx = json.loads((out / "index.json").read_text())
        self.assertEqual(idx["links"]["fi"]["reitit"], "links/reitit_fi.kml")
        self.assertEqual(idx["link_packages"]["en"]["reitit"], "links/reitit_en_link.zip")
        ns = {"k": "http://www.opengis.net/kml/2.2"}
        root = ET.parse(out / "links/reitit_fi.kml").getroot()
        self.assertEqual(root.find("k:Document/k:name", ns).text, "Lipas – Kaikki reitit")
        top = root.find("k:Document/k:Folder", ns)
        # config order; a type with subtypes is a subfolder of links
        self.assertEqual([c.find("k:name", ns).text for c in top if c.tag.endswith(("Folder", "NetworkLink"))],
                         ["Kävely", "Vaellus", "Moottorikelkkailu"])
        sled_folder = top.findall("k:Folder", ns)[1]
        self.assertEqual([n.find("k:name", ns).text for n in sled_folder.findall("k:NetworkLink", ns)],
                         ["Moottorikelkkareitit", "Moottorikelkkaurat"])
        self.assertEqual([n.find("k:name", ns).text for n in top.findall("k:Folder", ns)[0]
                          .findall("k:NetworkLink", ns)], ["Luontopolut"])
        # not in the all-areas link (parks and regions already contain their routes)
        all_root = ET.parse(out / "links/all_fi.kml").getroot()
        self.assertNotIn("Kaikki reitit", [f.find("k:name", ns).text for f in all_root.iter(
            "{http://www.opengis.net/kml/2.2}Folder")])

        layers = {e["slug"]: e for e in idx["areas"] if e["category"] == "reitit" and e["lang"] == "fi"}
        sled = layers["moottorikelkkareitit"]
        self.assertEqual(set(sled["files"]), {"kmz", "network_link", "link_package"})
        self.assertEqual(set(sled["uids"]), {"lipas-900022"})
        self.assertEqual(set(layers["moottorikelkkaurat"]["uids"]), {"lipas-900023"})
        self.assertEqual(sled["parent"], "moottorikelkkailu")
        self.assertIn("lipas-900020", layers["luontopolut"]["uids"])
        with zipfile.ZipFile(out / sled["files"]["kmz"]) as z:
            self.assertIn("Nuuksion moottorikelkkareitti", z.read("doc.kml").decode())
        # Snowmobile routes are only in the route type layer
        for e in idx["areas"]:
            if e["category"] != "reitit":
                self.assertNotIn("lipas-900022", e["uids"], e["key"])
                self.assertNotIn("lipas-900023", e["uids"], e["key"])
        self.assertTrue((out / "share/fi/reitit.html").exists())

    def test_link_packages(self):
        """Package that adds a refreshing KML link to ATAK (same structure as ATAK's own export)."""
        self.run_once()
        out = self.tmp / "out"
        idx = json.loads((out / "index.json").read_text())
        self.assertEqual(idx["link_packages"]["fi"]["all"], "links/all_fi_link.zip")
        park = next(e for e in idx["areas"] if e["key"] == "kansallispuistot/nuuksio" and e["lang"] == "fi")
        with zipfile.ZipFile(out / park["files"]["link_package"]) as z:
            names = z.namelist()
            m = ET.fromstring(z.read("MANIFEST/manifest.xml"))
            entry = next(c.get("zipEntry") for c in m.iter("Content"))
            self.assertIn(entry, names)
            params = {p.get("name"): p.get("value") for p in m.iter("Parameter")}
            self.assertEqual(params["contentType"], "Remote Resource")
            ev = ET.fromstring(z.read(entry))
        self.assertEqual(ev.get("type"), "b-i-r-r")
        rr = ev.find("detail/RemoteResources/RemoteResource")
        self.assertEqual(rr.get("url"), "https://example.org/lipas2tak/fi/kansallispuistot/nuuksio/nuuksio_fi.kml")
        self.assertEqual(rr.get("type"), "KML")
        self.assertEqual(rr.get("refreshSeconds"), "86400")
        self.assertEqual(rr.get("deleteOnExit"), "false")
        self.assertGreater(ev.get("stale"), "2030")
        # deterministic
        first = (out / park["files"]["link_package"]).read_bytes()
        self.run_once()
        self.assertEqual(first, (out / park["files"]["link_package"]).read_bytes())

    def test_change_detection(self):
        self.run_once()
        res = self.run_once()
        self.assertEqual(res["changes"], {})
        # remove one feature -> shows up as a deletion
        self.raw.sites = [s for s in self.raw.sites if s["lipas-id"] != 900002]
        res = self.run_once()
        self.assertIn("lipas-900002", res["changes"]["kansallispuistot/nuuksio/fi"]["removed"])
        out = self.tmp / "out"
        with zipfile.ZipFile(out / "fi/kansallispuistot/nuuksio/nuuksio_fi.zip") as z:
            self.assertFalse(any(n.startswith("lipas-900002/") for n in z.namelist()))


class ScheduleTests(unittest.TestCase):
    def test_next_slot(self):
        from zoneinfo import ZoneInfo
        from lipas2tak.cli import next_slot, parse_at
        tz, at = ZoneInfo("Europe/Helsinki"), parse_at("mon 04:00")
        self.assertEqual(at, (0, 4, 0))
        utc = timezone.utc
        # Tue 20.10.2026 -> Mon 26.10. 04:00 EET (winter time: UTC+2)
        self.assertEqual(next_slot(datetime(2026, 10, 20, 20, 0, tzinfo=utc), at, tz),
                         datetime(2026, 10, 26, 2, 0, tzinfo=utc))
        # Summer time (UTC+3); exactly at the slot -> the next week
        self.assertEqual(next_slot(datetime(2026, 6, 1, 1, 0, tzinfo=utc), at, tz),
                         datetime(2026, 6, 8, 1, 0, tzinfo=utc))
        self.assertEqual(next_slot(datetime(2026, 6, 1, 0, 59, tzinfo=utc), at, tz),
                         datetime(2026, 6, 1, 1, 0, tzinfo=utc))
        with self.assertRaises(SystemExit):
            parse_at("monday 25:00")


if __name__ == "__main__":
    unittest.main()

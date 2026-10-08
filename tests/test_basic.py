"""Testit: python -m unittest discover -s tests  (toimii myös pytestillä)."""
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

from lipas2tak import geo, pipeline
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
        b = [(24.02, 60.0), (24.01, 60.0)]  # vastakkaiseen suuntaan
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
        outside = (25.005, 60.5)  # ~280 m itään
        self.assertFalse(a.within(outside))
        self.assertTrue(a.within(outside, buffer_m=500))


class FormatTests(unittest.TestCase):
    def test_argb_matches_atak_example(self):
        # ATAKin esimerkkireitin väri -8454017 = 0xFF7F007F
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
        self.assertIn(("maakunnat/kanta-hame", "fi"), keys)  # akselijärjestys korjattu

        park = next(e for e in idx["areas"] if e["key"] == "kansallispuistot/nuuksio" and e["lang"] == "fi")
        uids = set(park["uids"])
        self.assertIn("lipas-900020", uids)          # Haukankierros yhdistetty yhdeksi viivaksi
        with zipfile.ZipFile(out / park["files"]["datapackage"]) as z:
            r = ET.fromstring(z.read("lipas-900020/lipas-900020.cot"))
        self.assertEqual(r.get("type"), "b-m-r")      # reitit navigoitavina reitteinä
        self.assertNotIn("lipas-900008", uids)       # Testilaavu suodatettu
        self.assertIn("osm-n1002", uids)             # OSM-käymälä retkikohteen lähellä
        self.assertNotIn("osm-n1001", uids)          # duplikaatti LOI-käymälän kanssa
        self.assertFalse(any(u.startswith("osm-w2001") for u in uids))  # Helsingin WC pois
        self.assertEqual(park["counts"]["kota"], 1)
        self.assertIn("osm-n3002", uids)             # OSM-laavu, jota ei ole Lipaksessa
        self.assertNotIn("osm-n3001", uids)          # sama laavu kuin Lipaksessa
        self.assertNotIn("osm-n3003", uids)          # ei retkikohteiden lähellä

        # Datapaketti: manifest + CoT parsittavissa, hashtagit remarksissa
        dp = out / park["files"]["datapackage"]
        with zipfile.ZipFile(dp) as z:
            ET.fromstring(z.read("MANIFEST/manifest.xml"))
            ev = ET.fromstring(z.read("lipas-900001/lipas-900001.cot"))
        rem = ev.find("detail/remarks").text
        self.assertIn("#laavu", rem)
        self.assertIn("#nuuksio", rem)
        self.assertIn("#uusimaa", rem)
        self.assertIn("WC", rem)
        icon = ev.find("detail/usericon").get("iconsetpath")
        self.assertTrue(icon.endswith("/Retkeily/laavu.png"))

        # KMZ: doc.kml parsittavissa ja kuvakkeet mukana
        with zipfile.ZipFile(out / park["files"]["kmz"]) as z:
            ET.fromstring(z.read("doc.kml"))
            self.assertIn("files/laavu.png", z.namelist())

        # GPX ilman korkeutta
        with zipfile.ZipFile(out / park["files"]["gpx_zip"]) as z:
            g = z.read(z.namelist()[0]).decode()
        self.assertNotIn("<ele>", g)
        ET.fromstring(g)

    def test_change_detection(self):
        self.run_once()
        res = self.run_once()
        self.assertEqual(res["changes"], {})
        # poistetaan yksi kohde -> näkyy poistona
        self.raw.sites = [s for s in self.raw.sites if s["lipas-id"] != 900002]
        res = self.run_once()
        self.assertIn("lipas-900002", res["changes"]["kansallispuistot/nuuksio/fi"]["removed"])
        out = self.tmp / "out"
        with zipfile.ZipFile(out / "fi/kansallispuistot/nuuksio/nuuksio_fi.zip") as z:
            self.assertFalse(any(n.startswith("lipas-900002/") for n in z.namelist()))


if __name__ == "__main__":
    unittest.main()

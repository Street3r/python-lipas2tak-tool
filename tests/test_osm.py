"""Overpass: incomplete results must not replace a good cached result."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lipas2tak.sources import osm
from lipas2tak.sources.http import CachedClient

URL = "https://overpass.example/api/interpreter"
TAGS = {"tourism": "viewpoint"}


def response(payload):
    r = mock.Mock(status_code=200)
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


def elements(n):
    return [{"type": "node", "id": i, "lat": 60.0, "lon": 24.0} for i in range(n)]


class OverpassTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.client = CachedClient(self.tmp, max_age_h=0, delay_s=0)
        self.client.BACKOFF_S = (0,)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def fetch(self, *payloads):
        with mock.patch.object(self.client.session, "post", side_effect=[response(p) for p in payloads]):
            return osm.fetch(self.client, [URL], TAGS)

    def test_error_remark_falls_back_to_previous_result(self):
        self.assertEqual(len(self.fetch({"elements": elements(100)})), 100)
        partial = {"elements": elements(5), "remark": 'runtime error: Query timed out in "query" at line 1'}
        self.assertEqual(len(self.fetch(*[partial] * 4)), 100)
        # The rejected result did not overwrite the cache
        self.assertEqual(len(self.fetch(*[partial] * 4)), 100)

    def test_far_fewer_elements_than_before_is_rejected(self):
        self.fetch({"elements": elements(100)})
        self.assertEqual(len(self.fetch(*[{"elements": elements(10)}] * 4)), 100)

    def test_retry_gets_the_complete_result(self):
        self.fetch({"elements": elements(100)})
        self.assertEqual(len(self.fetch({"elements": elements(10)}, {"elements": elements(98)})), 98)

    def test_small_previous_result_is_not_compared(self):
        self.fetch({"elements": elements(10)})
        self.assertEqual(len(self.fetch({"elements": elements(2)})), 2)

    def test_check_complete(self):
        osm.check_complete({"elements": [], "remark": "note: nothing found"})
        with self.assertRaises(ValueError):
            osm.check_complete({"elements": [], "remark": "runtime error: Query run out of memory"})


if __name__ == "__main__":
    unittest.main()

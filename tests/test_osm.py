"""Overpass: incomplete results must not replace a good cached result."""
from __future__ import annotations

import shutil
import tempfile
import time
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

    def test_time_budget_used_up_uses_cache_without_querying(self):
        self.fetch({"elements": elements(100)})
        with mock.patch.object(self.client.session, "post") as post:
            els = osm.fetch(self.client, [URL, URL + "2"], TAGS, deadline=time.time() - 1)
        post.assert_not_called()
        self.assertEqual(len(els), 100)
        self.assertEqual(len(self.client.stale), 1)

    def test_deadline_stops_retries(self):
        self.client.BACKOFF_S = (60,)
        bad = {"elements": [], "remark": "runtime error: Query timed out"}
        with mock.patch.object(self.client.session, "post", side_effect=[response(bad)] * 4) as post, \
                mock.patch("time.sleep") as sleep:
            with self.assertRaises(RuntimeError):
                self.client.get_json(URL, method="POST", data={"data": "q"}, validate=lambda d: osm.check_complete(d),
                                     deadline=time.time() + 30)
        self.assertEqual(post.call_count, 1)   # the 60 s pause would pass the deadline
        sleep.assert_not_called()

    def test_stale_copy_is_recorded(self):
        def has_features(d):
            if not d.get("features"):
                raise ValueError("empty")
        with mock.patch.object(self.client.session, "get", side_effect=[response({"features": [1, 2]})]):
            self.client.get_json(URL, validate=has_features)
        with mock.patch.object(self.client.session, "get", side_effect=[response({"features": []})] * 4):
            data = self.client.get_json(URL, validate=has_features, stale_ok=True)
        self.assertEqual(data, {"features": [1, 2]})                  # empty answer did not replace it
        self.assertEqual([u for u, _ in self.client.stale], [URL])

    def test_check_complete(self):
        osm.check_complete({"elements": [], "remark": "note: nothing found"})
        with self.assertRaises(ValueError):
            osm.check_complete({"elements": [], "remark": "runtime error: Query run out of memory"})


if __name__ == "__main__":
    unittest.main()

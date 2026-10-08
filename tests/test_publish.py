"""Publisher test against a local bare git repository."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from lipas2tak import publish
from lipas2tak.config import load_settings

FIXTURE = Path(__file__).parent / "fixtures" / "nuuksio"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


@unittest.skipUnless(shutil.which("git"), "git not installed")
class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.remote = self.tmp / "remote.git"
        git(self.tmp, "init", "-q", "--bare", str(self.remote))
        os.environ["LIPAS2TAK_ICONS_DIR"] = "/nonexistent/custom-icons"   # must be ignored
        self.settings = load_settings()
        self.kw = dict(raw_dir=FIXTURE, workdir=self.tmp / "work", repo_url=str(self.remote),
                       branch="data", base_url="https://example.github.io/repo/")

    def tearDown(self):
        os.environ.pop("LIPAS2TAK_ICONS_DIR", None)
        shutil.rmtree(self.tmp)

    def test_publish_cycle(self):
        t1 = datetime(2026, 10, 8, tzinfo=timezone.utc)
        self.assertTrue(publish.publish(self.settings, now=t1, **self.kw).startswith("published"))
        files = git(self.remote, "ls-tree", "-r", "--name-only", "data").splitlines()
        self.assertIn("links/all_fi.kml", files)
        self.assertIn("share/en/kansallispuistot.html", files)
        self.assertIn("CHANGELOG.md", files)
        self.assertIn(".nojekyll", files)
        self.assertFalse(any("_suojat.kmz" in f for f in files))       # no per-group KMZ
        kml = git(self.remote, "show", "data:links/all_fi.kml")
        self.assertIn("https://example.github.io/repo/fi/kansallispuistot/nuuksio/nuuksio_fi.kmz", kml)
        idx = json.loads(git(self.remote, "show", "data:index.json"))
        self.assertEqual(idx["public_base_url"], "https://example.github.io/repo")

        # Same data a week later: nothing to push
        t2 = datetime(2026, 10, 15, tzinfo=timezone.utc)
        self.assertEqual(publish.publish(self.settings, now=t2, **self.kw), "unchanged")

        # Changed data: new single commit (no history), changelog keeps both entries
        raw = self.tmp / "raw"
        shutil.copytree(FIXTURE, raw)
        sites = json.loads((raw / "sites.json").read_text())
        sites[0]["name"] = sites[0]["name"] + " (uusi nimi)"
        (raw / "sites.json").write_text(json.dumps(sites))
        self.kw["raw_dir"] = raw
        t3 = datetime(2026, 10, 22, tzinfo=timezone.utc)
        self.assertTrue(publish.publish(self.settings, now=t3, **self.kw).startswith("published"))
        self.assertEqual(git(self.remote, "rev-list", "--count", "data"), "1")
        log = git(self.remote, "show", "data:CHANGELOG.md")
        self.assertIn("## 2026-10-22", log)
        self.assertIn("## 2026-10-08", log)
        self.assertIn("kansallispuistot/nuuksio: +0 new, -0 removed, ~1 changed", log)


if __name__ == "__main__":
    unittest.main()

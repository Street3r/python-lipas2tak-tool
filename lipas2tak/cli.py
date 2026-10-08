"""Command line: `lipas2tak run|fetch|build|schedule`."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import __version__, normalize, pipeline
from .config import load_settings


def _settings(args):
    return load_settings(args.config, args.types)


def cmd_fetch(args) -> int:
    s = _settings(args)
    raw = pipeline.fetch_raw(s, normalize.Classifier(s))
    raw.dump(Path(args.dump))
    print(f"Raw data saved: {args.dump} ({len(raw.sites)} Lipas sites, {len(raw.lois)} LOIs)")
    return 0


def cmd_build(args) -> int:
    s = _settings(args)
    raw = pipeline.RawData.load(Path(args.raw))
    res = pipeline.run(s, raw, only=args.only)
    _summary(res)
    return 0


def cmd_run(args) -> int:
    s = _settings(args)
    raw = pipeline.fetch_raw(s, normalize.Classifier(s))
    if args.dump:
        raw.dump(Path(args.dump))
    res = pipeline.run(s, raw, only=args.only)
    _summary(res)
    return 0


def cmd_schedule(args) -> int:
    """Simple scheduler for containers: run now and then every N days."""
    log = logging.getLogger("schedule")
    interval = timedelta(days=args.every_days)
    while True:
        start = datetime.now(timezone.utc)
        try:
            cmd_run(args)
        except Exception:  # pragma: no cover - the scheduler keeps going after errors
            log.exception("Run failed; retrying in 6 h")
            time.sleep(6 * 3600)
            continue
        nxt = start + interval
        log.info("Next run %s", nxt.isoformat())
        time.sleep(max(60.0, (nxt - datetime.now(timezone.utc)).total_seconds()))


def _summary(res: dict) -> None:
    idx = res["index"]
    print(f"Features in total: {res['features']}")
    for e in idx["areas"]:
        total = sum(e["counts"].values())
        print(f"  [{e['lang']}] {e['key']}: {total} features -> {', '.join(sorted(e['files']))}")
    for lang, links in (idx.get("links") or {}).items():
        print(f"  KML network links [{lang}]: {', '.join(sorted(links.values()))}")
    if res["changes"]:
        print("Changes since the previous run:")
        for k, v in res["changes"].items():
            print(f"  {k}: +{len(v['added'])} -{len(v['removed'])} ~{len(v['modified'])}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="lipas2tak", description="Lipas -> TAK (CoT data packages, KMZ, GPX)")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--config")
    p.add_argument("--types")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="fetch raw data and save it as JSON files")
    f.add_argument("--dump", required=True, help="target directory")
    f.set_defaults(func=cmd_fetch)

    b = sub.add_parser("build", help="build outputs from saved raw data (no network)")
    b.add_argument("--raw", required=True)
    b.add_argument("--only", nargs="*", help="areas, e.g. kansallispuistot/nuuksio or nuuksio")
    b.set_defaults(func=cmd_build)

    r = sub.add_parser("run", help="fetch and build")
    r.add_argument("--only", nargs="*")
    r.add_argument("--dump", help="also save the raw data to this directory")
    r.set_defaults(func=cmd_run)

    sc = sub.add_parser("schedule", help="run repeatedly (container use)")
    sc.add_argument("--every-days", type=float, default=7)
    sc.add_argument("--only", nargs="*")
    sc.add_argument("--dump")
    sc.set_defaults(func=cmd_schedule)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

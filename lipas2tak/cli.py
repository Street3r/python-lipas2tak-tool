"""Komentorivi: `lipas2tak run|fetch|build|schedule`."""
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
    print(f"Raakadata tallennettu: {args.dump} ({len(raw.sites)} Lipas-kohdetta, {len(raw.lois)} LOI:ta)")
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
    """Yksinkertainen ajastin kontille: ajo heti ja sitten N päivän välein."""
    log = logging.getLogger("schedule")
    interval = timedelta(days=args.every_days)
    while True:
        start = datetime.now(timezone.utc)
        try:
            cmd_run(args)
        except Exception:  # pragma: no cover - ajastin jatkaa virheestä huolimatta
            log.exception("Ajo epäonnistui; yritetään uudelleen 6 h päästä")
            time.sleep(6 * 3600)
            continue
        nxt = start + interval
        log.info("Seuraava ajo %s", nxt.isoformat())
        time.sleep(max(60.0, (nxt - datetime.now(timezone.utc)).total_seconds()))


def _summary(res: dict) -> None:
    idx = res["index"]
    print(f"Kohteita yhteensä: {res['features']}")
    for e in idx["areas"]:
        total = sum(e["counts"].values())
        print(f"  [{e['lang']}] {e['key']}: {total} kohdetta -> {', '.join(sorted(e['files']))}")
    if res["changes"]:
        print("Muutokset edelliseen ajoon:")
        for k, v in res["changes"].items():
            print(f"  {k}: +{len(v['added'])} -{len(v['removed'])} ~{len(v['modified'])}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="lipas2tak", description="Lipas -> TAK (CoT, datapaketit, KMZ, GPX)")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--config")
    p.add_argument("--types")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="hae raakadata ja tallenna JSON-tiedostoiksi")
    f.add_argument("--dump", required=True, help="kohdehakemisto")
    f.set_defaults(func=cmd_fetch)

    b = sub.add_parser("build", help="tuota tiedostot tallennetusta raakadatasta (ei verkkoa)")
    b.add_argument("--raw", required=True)
    b.add_argument("--only", nargs="*", help="alueet, esim. kansallispuistot/nuuksio tai nuuksio")
    b.set_defaults(func=cmd_build)

    r = sub.add_parser("run", help="hae ja tuota")
    r.add_argument("--only", nargs="*")
    r.add_argument("--dump", help="tallenna myös raakadata tähän hakemistoon")
    r.set_defaults(func=cmd_run)

    sc = sub.add_parser("schedule", help="aja toistuvasti (konttikäyttö)")
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

"""Command line: `lipas2tak run|fetch|build|schedule`."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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


def cmd_run(args, next_check=None) -> int:
    s = _settings(args)
    raw = pipeline.fetch_raw(s, normalize.Classifier(s))
    if args.dump:
        raw.dump(Path(args.dump))
    res = pipeline.run(s, raw, only=args.only, next_check=next_check)
    _summary(res)
    return 0


def cmd_publish(args) -> int:
    from . import publish
    s = _settings(args)
    missing = [n for n, v in (("--repo/PUBLISH_REPO", args.repo), ("--base-url/PUBLISH_BASE_URL", args.base_url))
               if not v]
    if missing:
        print("Missing: " + ", ".join(missing), file=sys.stderr)
        return 2
    kw = dict(raw_dir=Path(args.raw), workdir=Path(args.workdir), repo_url=args.repo, branch=args.branch,
              base_url=args.base_url, repo_name=args.repo_name, dry_run=args.dry_run,
              allow_shrink=args.allow_shrink)
    if args.watch:
        publish.watch(s, Path(args.watch), args.interval, **kw)
        return 0
    print(publish.publish(s, **kw))
    return 0


WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse_at(spec: str) -> tuple[int, int, int]:
    """'mon 04:00' -> (weekday 0-6, hour, minute)."""
    try:
        day, hm = spec.lower().split()
        hour, minute = (int(x) for x in hm.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
        return WEEKDAYS.index(day[:3]), hour, minute
    except ValueError:
        raise SystemExit(f"--at: expected e.g. 'mon 04:00', got {spec!r}")


def next_slot(after: datetime, at: tuple[int, int, int], tz: ZoneInfo) -> datetime:
    """First weekly slot (local time in `tz`) strictly after `after`, in UTC."""
    weekday, hour, minute = at
    local = after.astimezone(tz)
    day = local.date() + timedelta(days=(weekday - local.weekday()) % 7)
    for _ in range(3):
        slot = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
        if slot > after:
            return slot.astimezone(timezone.utc)
        day += timedelta(days=7)
    raise AssertionError("unreachable")


def _last_run(args) -> datetime | None:
    """Time of the previous run (output index.json), or None."""
    try:
        idx = _settings(args).path("output") / "index.json"
        return datetime.fromisoformat(json.loads(idx.read_text(encoding="utf-8"))["generated"])
    except (OSError, ValueError, KeyError):
        return None


def cmd_schedule(args) -> int:
    """Scheduler for containers.

    With --at (e.g. 'mon 04:00', local time in --tz) the run happens weekly at
    that time; on start it runs at once only if the previous scheduled run was
    missed (or with --run-now), so restarts and updates do not move the schedule.
    Without --at: run now and then every N days.
    """
    log = logging.getLogger("schedule")
    if not args.at:
        interval = timedelta(days=args.every_days)
        while True:
            start = datetime.now(timezone.utc)
            try:
                cmd_run(args, next_check=start + interval)
            except Exception:  # pragma: no cover - the scheduler keeps going after errors
                log.exception("Run failed; retrying in 6 h")
                time.sleep(6 * 3600)
                continue
            nxt = start + interval
            log.info("Next run %s", nxt.isoformat())
            time.sleep(max(60.0, (nxt - datetime.now(timezone.utc)).total_seconds()))

    at, tz = parse_at(args.at), ZoneInfo(args.tz)
    now = datetime.now(timezone.utc)
    last = _last_run(args)
    due = args.run_now or last is None or next_slot(last, at, tz) <= now
    if not due:
        log.info("Previous run %s is up to date; waiting for the schedule (%s %s)",
                 last.isoformat(timespec="seconds"), args.at, args.tz)
    while True:
        if due:
            try:
                cmd_run(args, next_check=next_slot(datetime.now(timezone.utc), at, tz))
            except Exception:  # pragma: no cover - the scheduler keeps going after errors
                log.exception("Run failed; retrying in 6 h")
                nxt = next_slot(datetime.now(timezone.utc), at, tz)
                time.sleep(max(60.0, min(6 * 3600, (nxt - datetime.now(timezone.utc)).total_seconds())))
                continue
        nxt = next_slot(datetime.now(timezone.utc), at, tz)
        log.info("Next run %s", nxt.astimezone(tz).isoformat(timespec="minutes"))
        time.sleep(max(60.0, (nxt - datetime.now(timezone.utc)).total_seconds()))
        due = True


def _summary(res: dict) -> None:
    idx = res["index"]
    print(f"Features in total: {res['features']}")
    for e in idx["areas"]:
        total = sum(e["counts"].values())
        print(f"  [{e['lang']}] {e['key']}: {total} features -> {', '.join(sorted(e['files']))}")
    for lang, links in (idx.get("links") or {}).items():
        print(f"  KML network links [{lang}]: {', '.join(sorted(links.values()))}")
    if res.get("warnings"):
        print("Quality warnings:")
        for w in res["warnings"]:
            print(f"  {w}")
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
    sc.add_argument("--every-days", type=float, default=7, help="interval when --at is not given")
    sc.add_argument("--at", default=os.environ.get("LIPAS2TAK_SCHEDULE_AT", ""),
                    help="fixed weekly time, e.g. 'mon 04:00' (env LIPAS2TAK_SCHEDULE_AT)")
    sc.add_argument("--tz", default=os.environ.get("LIPAS2TAK_TZ", "Europe/Helsinki"),
                    help="time zone of --at (env LIPAS2TAK_TZ, default Europe/Helsinki)")
    sc.add_argument("--run-now", action="store_true", help="with --at: also run once at start")
    sc.add_argument("--only", nargs="*")
    sc.add_argument("--dump")
    sc.set_defaults(func=cmd_schedule)

    pb = sub.add_parser("publish", help="build the public version and push it to a git branch")
    pb.add_argument("--raw", required=True, help="raw data directory (from --dump)")
    pb.add_argument("--workdir", default="data/publish", help="build and git working directory")
    pb.add_argument("--repo", default=os.environ.get("PUBLISH_REPO"), help="git URL (env PUBLISH_REPO)")
    pb.add_argument("--branch", default=os.environ.get("PUBLISH_BRANCH", "data"))
    pb.add_argument("--base-url", default=os.environ.get("PUBLISH_BASE_URL"),
                    help="public URL of the branch, e.g. GitHub Pages (env PUBLISH_BASE_URL)")
    pb.add_argument("--repo-name", default=os.environ.get("PUBLISH_REPO_NAME", "finland-outdoor-tak-data"))
    pb.add_argument("--watch", help="generator index.json; publish whenever it changes")
    pb.add_argument("--interval", type=float, default=600, help="watch interval in seconds")
    pb.add_argument("--dry-run", action="store_true", help="build and commit locally, do not push")
    pb.add_argument("--allow-shrink", action="store_true",
                    help="publish even if the build has far fewer features than the published version "
                         "(limit: env PUBLISH_MAX_SHRINK, default 0.10)")
    pb.set_defaults(func=cmd_publish)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

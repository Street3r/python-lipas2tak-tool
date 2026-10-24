"""OpenStreetMap Overpass queries (e.g. toilets and shelters missing from Lipas).

OSM data © OpenStreetMap contributors, ODbL 1.0.
"""
from __future__ import annotations

import logging

from .http import CachedClient

log = logging.getLogger(__name__)


BBox = tuple[float, float, float, float]   # south, west, north, east


def build_query(tags: dict[str, str], bboxes: list[BBox] | None = None) -> str:
    """All of Finland, or only the given bounding boxes (e.g. around protected areas)."""
    filt = "".join(f'["{k}"="{v}"]' for k, v in tags.items())
    if bboxes:
        parts = "".join(f"{t}{filt}({s:.4f},{w:.4f},{n:.4f},{e:.4f});"
                        for s, w, n, e in bboxes for t in ("node", "way"))
        return f"[out:json][timeout:300];({parts});out center tags;"
    return (
        "[out:json][timeout:300];"
        'area["ISO3166-1"="FI"][admin_level=2]->.fi;'
        f"(node{filt}(area.fi);way{filt}(area.fi););"
        "out center tags;"
    )


# A new result with fewer than this share of the previous result's elements is
# treated as incomplete. OSM data does not shrink by half in a week.
MIN_RATIO = 0.5
MIN_PREVIOUS = 20   # below this the previous result is too small to compare with


def check_complete(data: dict, min_elements: int = 0) -> None:
    """Raise ValueError if an Overpass response is incomplete.

    A busy Overpass server can answer HTTP 200 with only part of the elements and
    a "remark" such as "runtime error: Query timed out ..." or "... out of memory".
    """
    remark = str(data.get("remark") or "")
    if "error" in remark.lower():
        raise ValueError(f"incomplete Overpass result: {remark}")
    n = len(data.get("elements", []))
    if n < min_elements:
        raise ValueError(f"Overpass returned {n} elements, expected at least {min_elements} "
                         f"(previous result); treating it as incomplete")


def fetch(client: CachedClient, overpass_urls: str | list[str], tags: dict[str, str],
          bboxes: list[BBox] | None = None) -> list[dict]:
    """Query Overpass; tries each server in turn (public servers are often busy: 504/429).

    Incomplete results (error remark, or far fewer elements than the previous
    result) are rejected like failed requests. If every server fails, the previous
    cached result is used, so a busy Overpass does not make OSM features disappear
    from the output.
    """
    urls = [overpass_urls] if isinstance(overpass_urls, str) else list(overpass_urls)
    q = build_query(tags, bboxes)
    prev = next((d for u in urls if (d := client.cached(u, method="POST", data={"data": q}, quiet=True))
                 is not None), None)
    prev_n = len(prev.get("elements", [])) if prev else 0
    min_elements = int(prev_n * MIN_RATIO) if prev_n >= MIN_PREVIOUS else 0
    last: Exception | None = None
    for i, url in enumerate(urls):
        is_last = i == len(urls) - 1
        try:
            data = client.get_json(url, method="POST", data={"data": q}, retries=4, timeout_s=330,
                                   stale_ok=False,
                                   validate=lambda d: check_complete(d, min_elements))
            break
        except RuntimeError as e:
            last = e
            log.warning("Overpass server failed: %s%s", url, "" if is_last else ", trying the next one")
    else:
        # Every server failed: fall back to the newest cached result of any server
        data = next((d for u in urls if (d := client.cached(u, method="POST", data={"data": q})) is not None),
                    None)
        if data is None:
            raise RuntimeError(f"All Overpass servers failed and no cached result: {tags}") from last
    els = data.get("elements", [])
    log.info("OSM %s: %d elements", tags, len(els))
    return els

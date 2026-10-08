"""OpenStreetMap Overpass queries (e.g. toilets and shelters missing from Lipas).

OSM data © OpenStreetMap contributors, ODbL 1.0.
"""
from __future__ import annotations

import logging

from .http import CachedClient

log = logging.getLogger(__name__)


def build_query(tags: dict[str, str]) -> str:
    filt = "".join(f'["{k}"="{v}"]' for k, v in tags.items())
    return (
        "[out:json][timeout:300];"
        'area["ISO3166-1"="FI"][admin_level=2]->.fi;'
        f"(node{filt}(area.fi);way{filt}(area.fi););"
        "out center tags;"
    )


def fetch(client: CachedClient, overpass_urls: str | list[str], tags: dict[str, str]) -> list[dict]:
    """Query Overpass; tries each server in turn (public servers are often busy: 504/429).

    If every server fails, the previous cached result is used, so a busy Overpass
    does not make OSM features disappear from the output.
    """
    urls = [overpass_urls] if isinstance(overpass_urls, str) else list(overpass_urls)
    q = build_query(tags)
    last: Exception | None = None
    for i, url in enumerate(urls):
        is_last = i == len(urls) - 1
        try:
            data = client.get_json(url, method="POST", data={"data": q}, retries=4, timeout_s=330,
                                   stale_ok=False)
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

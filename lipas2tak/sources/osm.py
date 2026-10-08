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


def fetch(client: CachedClient, overpass_url: str, tags: dict[str, str]) -> list[dict]:
    q = build_query(tags)
    data = client.get_json(overpass_url, method="POST", data={"data": q})
    els = data.get("elements", [])
    log.info("OSM %s: %d elements", tags, len(els))
    return els

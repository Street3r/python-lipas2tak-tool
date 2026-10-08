"""Regional (maakunta) boundaries from the Statistics Finland WFS service (CC BY 4.0)."""
from __future__ import annotations

import logging

from ..config import file_slug, slugify
from ..model import AreaDef, Localized
from .http import CachedClient

log = logging.getLogger(__name__)


def _fix_axis_order(geom: dict) -> dict:
    """Ensure (lon, lat) axis order. In Finland lat is ~59–71 and lon ~19–32."""

    def first_coord(c):
        while isinstance(c[0], list):
            c = c[0]
        return c

    c = first_coord(geom["coordinates"])
    if c[0] > 50:  # first value is latitude -> swap

        def swap(x):
            if isinstance(x[0], list):
                return [swap(y) for y in x]
            return [x[1], x[0]] + list(x[2:])

        geom = dict(geom, coordinates=swap(geom["coordinates"]))
    return geom


def fetch_regions(client: CachedClient, wfs_url: str, layer: str) -> list[AreaDef]:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": layer,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
    }
    data = client.get_json(wfs_url, params=params)
    return fetch_regions_from_features(data.get("features", []))


def fetch_regions_from_features(features: list[dict]) -> list[AreaDef]:
    out = []
    for f in features:
        p = f.get("properties") or {}
        fi = p.get("nimi") or p.get("name")
        en = p.get("name") or fi
        if not f.get("geometry"):
            continue
        out.append(AreaDef(
            slug=file_slug(fi),
            category="maakunnat",
            name=Localized(fi=fi, en=en),
            tag=slugify(fi),
            geometry=_fix_axis_order(f["geometry"]),
        ))
    log.info("Regions: %d", len(out))
    return out

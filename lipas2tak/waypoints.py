"""Reitin varren taukopaikat nimetyiksi reittipisteiksi (ATAK b-m-p-w, GPX rtept name)."""
from __future__ import annotations

import logging

from . import geo
from .model import Feature

log = logging.getLogger(__name__)


def attach_waypoints(features: list[Feature], kind_group: dict[str, str], groups: list[str],
                     radius_m: float = 75.0, snap_vertex_m: float = 10.0,
                     cluster_m: float = 200.0) -> None:
    """Liittää valittujen ryhmien pistekohteet niitä lähellä kulkeviin reitteihin.

    Kohde liitetään reittiin, jos se on enintään `radius_m` päässä reittiviivasta.
    Reittiviivaan lisätään kohdalle uusi solmu (tai käytetään olemassa olevaa,
    jos sellainen on alle `snap_vertex_m` päässä), ja solmu merkitään
    kohteen nimellä. Reittiviivan muoto ei muutu. Lähekkäiset kohteet
    (alle `cluster_m` toisistaan) yhdistetään yhdeksi reittipisteeksi, jonka
    nimenä on tärkeimmän kohteen nimi ja kuvauksena kaikkien kohteiden tyypit.
    """
    pts = [f for f in features if f.point is not None and kind_group.get(f.kind) in groups]
    grid = geo.GridIndex.for_radius(max(radius_m, 1000))
    for f in pts:
        grid.add(f.point, f)
    n_routes = n_wp = 0
    for r in features:
        if not r.lines:
            continue
        line = r.lines[0]
        cands = {}
        for c in line:
            for _, f in grid.near(c):
                cands[f.uid] = f
        hits = []
        for f in cands.values():
            snap = geo.snap_to_line(line, f.point, radius_m)
            if snap:
                hits.append((snap[0], snap[1], snap[2], f))
        if not hits:
            continue
        hits.sort(key=lambda h: (h[0], h[1]))
        # Ryppäät: peräkkäiset kohteet, jotka ovat alle cluster_m päässä toisistaan,
        # saavat yhden yhteisen reittipisteen (esim. laavu + nuotiopaikka + puuvaja)
        clusters: list[list] = []
        for h in hits:
            if clusters and geo.haversine(clusters[-1][-1][2], h[2]) <= cluster_m:
                clusters[-1].append(h)
            else:
                clusters.append([h])
        new_line = list(line)
        inserted: list[tuple[int, list[Feature]]] = []
        offset = 0
        for cl in clusters:
            # edustaja: tärkein ryhmä (groups-järjestys), sitten lähin viivaa
            rep = min(cl, key=lambda h: (groups.index(kind_group[h[3].kind]), h[0], h[1]))
            seg, t, q, _ = rep
            i = seg + offset
            a, b = new_line[i], new_line[i + 1]
            if geo.haversine(q, a) <= snap_vertex_m:
                idx = i
            elif geo.haversine(q, b) <= snap_vertex_m:
                idx = i + 1
            else:
                new_line.insert(i + 1, q)
                idx = i + 1
                offset += 1
            members = [rep[3]] + [h[3] for h in cl if h is not rep]
            inserted.append((idx, members))
        r.lines = [new_line]
        r.waypoints = inserted
        n_routes += 1
        n_wp += len(inserted)
    log.info("Reittipisteitä: %d kohdetta %d reitillä", n_wp, n_routes)

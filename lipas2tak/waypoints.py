"""Rest stops along routes as named waypoints (ATAK b-m-p-w, GPX rtept name)."""
from __future__ import annotations

import logging

from . import geo
from .model import Feature

log = logging.getLogger(__name__)


def attach_waypoints(features: list[Feature], kind_group: dict[str, str], groups: list[str],
                     radius_m: float = 75.0, snap_vertex_m: float = 10.0,
                     cluster_m: float = 200.0) -> None:
    """Attach point features of the selected groups to routes passing near them.

    A feature is attached if it is within `radius_m` of the route line. A new
    vertex is inserted on the line at that spot (or an existing vertex within
    `snap_vertex_m` is used) and named after the feature; the shape of the line
    does not change. Features closer than `cluster_m` to each other form one
    waypoint, named after the most important feature and described with the
    kinds of all features in the cluster.
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
        # Clusters: consecutive features closer than cluster_m to each other share
        # one waypoint (e.g. lean-to + campfire site + woodshed)
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
            # representative: most important group (order of `groups`), then position
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
    log.info("Waypoints: %d on %d routes", n_wp, n_routes)

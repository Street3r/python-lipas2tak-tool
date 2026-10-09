"""Lightweight geometry helpers without external dependencies.

Coordinates are always (lon, lat) in WGS84, as in GeoJSON. Distances are
computed in a local equirectangular projection, which is accurate enough
for distances of a few kilometres at Finnish latitudes.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

Coord = tuple[float, float]  # (lon, lat)
Line = list[Coord]

EARTH_R = 6371008.8


def drop_z(coords: Sequence[Sequence[float]]) -> Line:
    """Drop altitude (and any other extra values) from coordinates."""
    return [(float(c[0]), float(c[1])) for c in coords]


def haversine(a: Coord, b: Coord) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def line_length_m(line: Line) -> float:
    return sum(haversine(line[i], line[i + 1]) for i in range(len(line) - 1))


class LocalProjection:
    """Equirectangular projection to metres around the given latitude."""

    def __init__(self, lat0: float):
        self.kx = math.cos(math.radians(lat0)) * math.pi * EARTH_R / 180.0
        self.ky = math.pi * EARTH_R / 180.0

    def fwd(self, c: Coord) -> tuple[float, float]:
        return c[0] * self.kx, c[1] * self.ky


def _seg_dist(p, a, b) -> float:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - x1 - t * dx, y - y1 - t * dy)


def simplify(line: Line, tolerance_m: float) -> Line:
    """Douglas–Peucker simplification with a tolerance in metres (iterative)."""
    if len(line) < 3 or tolerance_m <= 0:
        return list(line)
    proj = LocalProjection(sum(c[1] for c in line) / len(line))
    pts = [proj.fwd(c) for c in line]
    keep = [False] * len(line)
    keep[0] = keep[-1] = True
    stack = [(0, len(line) - 1)]
    while stack:
        i0, i1 = stack.pop()
        dmax, idx = 0.0, -1
        for i in range(i0 + 1, i1):
            d = _seg_dist(pts[i], pts[i0], pts[i1])
            if d > dmax:
                dmax, idx = d, i
        if idx >= 0 and dmax > tolerance_m:
            keep[idx] = True
            stack.append((i0, idx))
            stack.append((idx, i1))
    return [c for c, k in zip(line, keep) if k]


def merge_lines(lines: Iterable[Line], snap_m: float = 5.0) -> list[Line]:
    """Join lines that connect end to end (linemerge), O(n).

    End points closer than `snap_m` metres are treated as the same node. Lines
    are chained through nodes where exactly two line ends meet. At junctions
    (>2 ends) the chain stops, so branches stay separate lines. Closed loops
    are kept as loops.
    """
    parts = [list(l) for l in lines if len(l) >= 2]
    if len(parts) <= 1:
        return parts

    # --- End-point nodes (grid + neighbouring cells) ---
    lat0 = sum(p[0][1] for p in parts) / len(parts)
    proj = LocalProjection(lat0)
    cell = max(snap_m, 0.5)
    grid: dict[tuple[int, int], list[tuple[float, float, int]]] = {}
    node_count = 0

    def node_of(c: Coord) -> int:
        nonlocal node_count
        x, y = proj.fwd(c)
        kx, ky = int(math.floor(x / cell)), int(math.floor(y / cell))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for nx, ny, nid in grid.get((kx + dx, ky + dy), ()):
                    if math.hypot(nx - x, ny - y) <= snap_m:
                        return nid
        nid = node_count
        node_count += 1
        grid.setdefault((kx, ky), []).append((x, y, nid))
        return nid

    edges = [(p, node_of(p[0]), node_of(p[-1])) for p in parts]
    adj: dict[int, list[int]] = {}
    for i, (_, a, b) in enumerate(edges):
        adj.setdefault(a, []).append(i)
        adj.setdefault(b, []).append(i)  # a loop (a == b) is counted twice

    used = [False] * len(edges)

    def oriented(i: int, from_node: int) -> tuple[Line, int]:
        line, a, b = edges[i]
        return (line, b) if a == from_node else (line[::-1], a)

    def walk(start_edge: int, from_node: int) -> Line:
        used[start_edge] = True
        coords, cur = oriented(start_edge, from_node)
        coords = list(coords)
        while len(adj[cur]) == 2:
            nxt = [e for e in adj[cur] if not used[e]]
            if not nxt:
                break
            used[nxt[0]] = True
            seg, cur2 = oriented(nxt[0], cur)
            coords.extend(seg[1:])
            cur = cur2
        return coords

    out: list[Line] = []
    # First the chains that start at an end point or a junction
    for node, es in adj.items():
        if len(es) != 2:
            for e in es:
                if not used[e]:
                    out.append(walk(e, node))
    # Whatever remains are closed loops
    for i, (_, a, _) in enumerate(edges):
        if not used[i]:
            out.append(walk(i, a))
    return out


def _bearing_out(line: Line, from_start: bool, proj: "LocalProjection", look_m: float = 25.0):
    """Unit vector pointing from a line end into the line (averaged over ~look_m)."""
    pts = line if from_start else line[::-1]
    x0, y0 = proj.fwd(pts[0])
    x1, y1 = x0, y0
    for c in pts[1:]:
        x1, y1 = proj.fwd(c)
        if math.hypot(x1 - x0, y1 - y0) >= look_m:
            break
    d = math.hypot(x1 - x0, y1 - y0)
    return ((x1 - x0) / d, (y1 - y0) / d) if d else (0.0, 0.0)


def _nodes(parts: list[Line], snap_m: float):
    """Node ids of the line ends: [(start node, end node)], with end points closer than snap_m merged."""
    lat0 = sum(p[0][1] for p in parts) / len(parts)
    proj = LocalProjection(lat0)
    cell = max(snap_m, 0.5)
    grid: dict[tuple[int, int], list[tuple[float, float, int]]] = {}
    count = 0

    def node_of(c: Coord) -> int:
        nonlocal count
        x, y = proj.fwd(c)
        kx, ky = int(math.floor(x / cell)), int(math.floor(y / cell))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for nx, ny, nid in grid.get((kx + dx, ky + dy), ()):
                    if math.hypot(nx - x, ny - y) <= snap_m:
                        return nid
        nid = count
        count += 1
        grid.setdefault((kx, ky), []).append((x, y, nid))
        return nid

    return [(node_of(p[0]), node_of(p[-1])) for p in parts], proj


def has_junction(lines: Iterable[Line], snap_m: float = 5.0) -> bool:
    """True if three or more line ends meet somewhere (the lines form a network)."""
    parts = [l for l in lines if len(l) >= 2]
    if len(parts) < 2:
        return False
    ends, _ = _nodes(parts, snap_m)
    deg: dict[int, int] = {}
    for a, b in ends:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    return any(v >= 3 for v in deg.values())


def merge_strokes(lines: Iterable[Line], snap_m: float = 5.0, max_turn_deg: float = 60.0) -> list[Line]:
    """Join lines into as few continuous lines ("strokes") as is natural.

    Like `merge_lines`, but a chain also continues through a junction: at a
    node where three or more line ends meet, ends are paired by the straightest
    continuation (smallest turn, at most `max_turn_deg`). A path network of many
    short pieces thus becomes a few long lines, and a ring path becomes a loop.
    """
    parts = [list(l) for l in lines if len(l) >= 2]
    if len(parts) <= 1:
        return parts
    ends, proj = _nodes(parts, snap_m)
    at: dict[int, list[tuple[int, int]]] = {}       # node -> [(edge, end 0/1)]
    for i, (a, b) in enumerate(ends):
        at.setdefault(a, []).append((i, 0))
        at.setdefault(b, []).append((i, 1))

    partner: dict[tuple[int, int], tuple[int, int]] = {}
    cos_limit = math.cos(math.radians(max_turn_deg))
    for node, es in at.items():
        if len(es) == 2:
            partner[es[0]], partner[es[1]] = es[1], es[0]
            continue
        if len(es) < 2:
            continue
        dirs = {e: _bearing_out(parts[e[0]], e[1] == 0, proj) for e in es}
        cands = []
        for x in range(len(es)):
            for y in range(x + 1, len(es)):
                u, v = dirs[es[x]], dirs[es[y]]
                straight = -(u[0] * v[0] + u[1] * v[1])   # 1 = straight on, -1 = U-turn
                if straight >= cos_limit:
                    cands.append((-straight, x, y))
        for _, x, y in sorted(cands):
            if es[x] not in partner and es[y] not in partner:
                partner[es[x]], partner[es[y]] = es[y], es[x]

    used = [False] * len(parts)

    def walk(edge: int, enter_end: int) -> Line:
        coords: Line = []
        while True:
            used[edge] = True
            seg = parts[edge] if enter_end == 0 else parts[edge][::-1]
            coords.extend(seg if not coords else seg[1:])
            nxt = partner.get((edge, 1 - enter_end))
            if nxt is None or used[nxt[0]]:
                return coords
            edge, enter_end = nxt

    out: list[Line] = []
    # Chains starting at a free end (dead end, or an unpaired end at a junction)
    for i in range(len(parts)):
        for e in (0, 1):
            if not used[i] and (i, e) not in partner:
                out.append(walk(i, e))
    # Whatever remains are closed loops
    for i in range(len(parts)):
        if not used[i]:
            out.append(walk(i, 0))
    return out


def is_closed(line: Line, snap_m: float = 5.0) -> bool:
    return len(line) > 2 and haversine(line[0], line[-1]) <= snap_m


def snap_to_line(line: Line, pt: Coord, max_dist_m: float):
    """Nearest point on the line: (segment index, t 0..1, point on line, distance m) or None."""
    proj = LocalProjection(pt[1])
    p = proj.fwd(pt)
    best = None
    prev = proj.fwd(line[0])
    for i in range(len(line) - 1):
        cur = proj.fwd(line[i + 1])
        dx, dy = cur[0] - prev[0], cur[1] - prev[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - prev[0]) * dx + (p[1] - prev[1]) * dy) / L2))
        qx, qy = prev[0] + t * dx, prev[1] + t * dy
        d = math.hypot(p[0] - qx, p[1] - qy)
        if d <= max_dist_m and (best is None or d < best[3]):
            a, b = line[i], line[i + 1]
            best = (i, t, (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])), d)
        prev = cur
    return best


class GridIndex:
    """Simple grid index for nearby-point queries.

    `near()` yields the points in the neighbouring cells; cell size is in
    degrees. Use `for_radius()` to get a cell size that covers a search radius.
    """

    def __init__(self, cell_deg: float = 0.01):
        self.cell = cell_deg
        self.cells: dict[tuple[int, int], list] = {}

    # Longitude cells are 3x wider so the radius is covered all over Finland (cos 70° ≈ 0.34)
    LON_FACTOR = 3

    @classmethod
    def for_radius(cls, radius_m: float) -> "GridIndex":
        return cls(cell_deg=max(0.005, radius_m / 111_000.0 * 1.1))

    def _key(self, c: Coord) -> tuple[int, int]:
        return int(math.floor(c[0] / (self.cell * self.LON_FACTOR))), int(math.floor(c[1] / self.cell))

    def add(self, c: Coord, value) -> None:
        self.cells.setdefault(self._key(c), []).append((c, value))

    def near(self, c: Coord):
        kx, ky = self._key(c)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                yield from self.cells.get((kx + dx, ky + dy), ())


# --- Polygons --------------------------------------------------------------

def _ring_contains(ring: Line, pt: Coord) -> bool:
    x, y = pt
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y):
            xin = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < xin:
                inside = not inside
        j = i
    return inside


class Area:
    """(Multi)Polygon area: containment and buffer tests with bbox pre-filtering.

    Large archipelago areas (thousands of polygons, hundreds of thousands of
    vertices) need pre-filtering: polygons and edge blocks (BLOCK vertices)
    have their own bboxes, so only nearby edges are checked.
    """

    BLOCK = 64

    def __init__(self, geometry: dict):
        t = geometry["type"]
        if t == "Polygon":
            polys = [geometry["coordinates"]]
        elif t == "MultiPolygon":
            polys = geometry["coordinates"]
        else:
            raise ValueError(f"Not an area geometry: {t}")
        self.polygons: list[list[Line]] = [[drop_z(r) for r in p] for p in polys]
        self.poly_bboxes = [_bbox(p[0]) for p in self.polygons]
        xs = [b[0] for b in self.poly_bboxes] + [b[2] for b in self.poly_bboxes]
        ys = [b[1] for b in self.poly_bboxes] + [b[3] for b in self.poly_bboxes]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))
        # Edge blocks: (bbox, vertices); consecutive blocks share an end vertex
        self.blocks: list[tuple[tuple[float, float, float, float], Line]] = []
        for poly in self.polygons:
            for ring in poly:
                for i in range(0, len(ring) - 1, self.BLOCK):
                    seg = ring[i:i + self.BLOCK + 1]
                    self.blocks.append((_bbox(seg), seg))

    @staticmethod
    def _margins(lat: float, buffer_m: float) -> tuple[float, float]:
        dy = buffer_m / 111_000.0
        return dy / max(0.2, math.cos(math.radians(lat))), dy

    @staticmethod
    def _bbox_hit(b, pt: Coord, mx: float, my: float) -> bool:
        return b[0] - mx <= pt[0] <= b[2] + mx and b[1] - my <= pt[1] <= b[3] + my

    def contains(self, pt: Coord) -> bool:
        if not self._bbox_hit(self.bbox, pt, 0, 0):
            return False
        for poly, b in zip(self.polygons, self.poly_bboxes):
            if not self._bbox_hit(b, pt, 0, 0):
                continue
            if _ring_contains(poly[0], pt) and not any(_ring_contains(h, pt) for h in poly[1:]):
                return True
        return False

    def _edge_distance(self, pt: Coord, limit_m: float) -> float:
        """Shortest distance to the boundary, checking only blocks within `limit_m`."""
        mx, my = self._margins(pt[1], limit_m)
        proj = LocalProjection(pt[1])
        p = proj.fwd(pt)
        best = math.inf
        for b, seg in self.blocks:
            if not self._bbox_hit(b, pt, mx, my):
                continue
            prev = proj.fwd(seg[0])
            for c in seg[1:]:
                cur = proj.fwd(c)
                d = _seg_dist(p, prev, cur)
                if d < best:
                    best = d
                prev = cur
        return best

    def distance_m(self, pt: Coord, limit_m: float = 50_000.0) -> float:
        """Distance to the area boundary in metres (0 inside, inf beyond `limit_m`)."""
        if self.contains(pt):
            return 0.0
        return self._edge_distance(pt, limit_m)

    def within(self, pt: Coord, buffer_m: float = 0.0) -> bool:
        mx, my = self._margins(pt[1], buffer_m)
        if not self._bbox_hit(self.bbox, pt, mx, my):
            return False
        if self.contains(pt):
            return True
        return buffer_m > 0 and self._edge_distance(pt, buffer_m) <= buffer_m

    def touches_line(self, line: Line, buffer_m: float = 0.0) -> bool:
        return any(self.within(c, buffer_m) for c in line)

    def length_within_m(self, line: Line, buffer_m: float = 0.0) -> tuple[float, float]:
        """(length inside the area, total length) in metres, based on vertices."""
        inside = [self.within(c, buffer_m) for c in line]
        tot = ins = 0.0
        for i in range(len(line) - 1):
            d = haversine(line[i], line[i + 1])
            tot += d
            if inside[i] and inside[i + 1]:
                ins += d
        return ins, tot


def _bbox(pts: Line) -> tuple[float, float, float, float]:
    xs = [c[0] for c in pts]
    ys = [c[1] for c in pts]
    return min(xs), min(ys), max(xs), max(ys)


def representative_point(geometry: dict) -> Coord:
    """Representative point: the point itself or the middle vertex of a line."""
    t = geometry["type"]
    c = geometry["coordinates"]
    if t == "Point":
        return float(c[0]), float(c[1])
    if t == "LineString":
        return tuple(c[len(c) // 2][:2])  # type: ignore[return-value]
    if t == "MultiLineString":
        longest = max(c, key=len)
        return tuple(longest[len(longest) // 2][:2])  # type: ignore[return-value]
    if t == "Polygon":
        ring = c[0]
        return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
    raise ValueError(t)

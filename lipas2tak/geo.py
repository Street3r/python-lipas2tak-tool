"""Kevyet geometriatyökalut ilman ulkoisia riippuvuuksia.

Koordinaatit ovat aina (lon, lat) WGS84:ssä, kuten GeoJSONissa.
Etäisyydet lasketaan paikallisessa tasoprojektiossa (equirectangular),
mikä riittää Suomen mittakaavassa muutaman kilometrin matkoille.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

Coord = tuple[float, float]  # (lon, lat)
Line = list[Coord]

EARTH_R = 6371008.8


def drop_z(coords: Sequence[Sequence[float]]) -> Line:
    """Pudottaa korkeuden (ja muut ylimääräiset arvot) koordinaateista."""
    return [(float(c[0]), float(c[1])) for c in coords]


def haversine(a: Coord, b: Coord) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def line_length_m(line: Line) -> float:
    return sum(haversine(line[i], line[i + 1]) for i in range(len(line) - 1))


class LocalProjection:
    """Equirectangular-projektio metreihin annetun leveysasteen ympärillä."""

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
    """Douglas–Peucker-yksinkertaistus metritoleranssilla (iteratiivinen)."""
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
    """Yhdistää päistään toisiinsa liittyvät viivat (linemerge), O(n).

    Päätepisteet, jotka ovat alle `snap_m` metrin päässä toisistaan, katsotaan
    samaksi solmuksi. Viivat ketjutetaan solmujen läpi, joissa kohtaa täsmälleen
    kaksi viivanpäätä. Haarautumiskohdissa (>2 päätä) ketju katkeaa, jolloin
    haarat jäävät omiksi viivoikseen. Suljetut silmukat säilyvät silmukoina.
    """
    parts = [list(l) for l in lines if len(l) >= 2]
    if len(parts) <= 1:
        return parts

    # --- Päätepisteiden solmut (ruudukko + naapuriruudut) ---
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
        adj.setdefault(b, []).append(i)  # silmukka (a == b) lasketaan kahdesti

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
    # Ensin ketjut, jotka alkavat päätepisteestä tai haarautumasta
    for node, es in adj.items():
        if len(es) != 2:
            for e in es:
                if not used[e]:
                    out.append(walk(e, node))
    # Jäljelle jäävät ovat suljettuja silmukoita
    for i, (_, a, _) in enumerate(edges):
        if not used[i]:
            out.append(walk(i, a))
    return out


class GridIndex:
    """Yksinkertainen ruudukkoindeksi lähipistehakuun.

    `near()` palauttaa pisteet viereisistä ruuduista; solukoko asteina.
    Oletus 0.01° ≈ 1.1 km (lat) / 0.55 km (lon Suomessa), mikä riittää
    alle ~500 m hakusäteille.
    """

    def __init__(self, cell_deg: float = 0.01):
        self.cell = cell_deg
        self.cells: dict[tuple[int, int], list] = {}

    def _key(self, c: Coord) -> tuple[int, int]:
        return int(math.floor(c[0] / (self.cell * 2))), int(math.floor(c[1] / self.cell))

    def add(self, c: Coord, value) -> None:
        self.cells.setdefault(self._key(c), []).append((c, value))

    def near(self, c: Coord):
        kx, ky = self._key(c)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                yield from self.cells.get((kx + dx, ky + dy), ())


# --- Polygonit -----------------------------------------------------------

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
    """(Multi)Polygon-alue: sisältyvyys- ja puskuritestit bbox-esisuodatuksella.

    Suuret saaristoalueet (tuhansia polygoneja ja satojatuhansia solmuja)
    vaativat esisuodatusta: polygoneilla ja reunapaloilla (BLOCK solmua)
    on omat bboxinsa, joten vain lähellä olevat reunat tarkistetaan.
    """

    BLOCK = 64

    def __init__(self, geometry: dict):
        t = geometry["type"]
        if t == "Polygon":
            polys = [geometry["coordinates"]]
        elif t == "MultiPolygon":
            polys = geometry["coordinates"]
        else:
            raise ValueError(f"Ei aluegeometria: {t}")
        self.polygons: list[list[Line]] = [[drop_z(r) for r in p] for p in polys]
        self.poly_bboxes = [_bbox(p[0]) for p in self.polygons]
        xs = [b[0] for b in self.poly_bboxes] + [b[2] for b in self.poly_bboxes]
        ys = [b[1] for b in self.poly_bboxes] + [b[3] for b in self.poly_bboxes]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))
        # Reunapalat: (bbox, solmut), peräkkäiset palat jakavat päätesolmun
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
        """Lyhin etäisyys reunaan, tarkistaen vain `limit_m` säteen palat."""
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
        """Etäisyys alueen reunaan metreinä (0 sisällä, inf jos yli `limit_m`)."""
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
        """(alueella oleva pituus, kokonaispituus) metreinä solmujen perusteella."""
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
    """Edustava piste: piste itse tai viivan keskimmäinen solmu."""
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

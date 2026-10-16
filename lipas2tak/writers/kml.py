"""KMZ (doc.kml + icons) and KML network link (NetworkLink)."""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from .xmltext import escape, quoteattr

from .. import attribution
from ..geo import Coord, Line
from . import ziputil


def kml_color(hex_rgb: str, alpha: int = 255) -> str:
    """'#RRGGBB' -> KML aabbggrr."""
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"{alpha:02x}{b}{g}{r}".lower()


@dataclass
class Placemark:
    id: str
    name: str
    description: str
    style: str
    point: Coord | None = None
    lines: list[Line] = field(default_factory=list)


@dataclass
class Folder:
    name: str
    placemarks: list[Placemark] = field(default_factory=list)


def _coords(line: Line) -> str:
    return " ".join(f"{lon:.6f},{lat:.6f}" for lon, lat in line)


def _placemark(p: Placemark) -> str:
    if p.point is not None:
        geom = (f"<Point><altitudeMode>clampToGround</altitudeMode>"
                f"<coordinates>{p.point[0]:.6f},{p.point[1]:.6f}</coordinates></Point>")
    elif len(p.lines) == 1:
        geom = (f"<LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>"
                f"<coordinates>{_coords(p.lines[0])}</coordinates></LineString>")
    else:
        geom = "<MultiGeometry>" + "".join(
            f"<LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>"
            f"<coordinates>{_coords(l)}</coordinates></LineString>" for l in p.lines) + "</MultiGeometry>"
    return (f"<Placemark id={quoteattr(p.id)}><name>{escape(p.name)}</name>"
            f"<description>{escape(p.description)}</description>"
            f"<styleUrl>#{p.style}</styleUrl>{geom}</Placemark>")


def write_kmz(path: Path, name: str, folders: list[Folder], icon_styles: dict[str, str],
              line_styles: dict[str, tuple[str, float]], icons_dir) -> None:
    """icon_styles: {style_id: icon file}, line_styles: {style_id: (#RRGGBB, width)}"""
    styles = []
    used_icons = set()
    for sid, icon in icon_styles.items():
        used_icons.add(icon)
        styles.append(f'<Style id="{sid}"><IconStyle><scale>1.0</scale>'
                      f"<Icon><href>files/{escape(icon)}</href></Icon></IconStyle></Style>")
    for sid, (color, width) in line_styles.items():
        styles.append(f'<Style id="{sid}"><LineStyle><color>{kml_color(color)}</color>'
                      f"<width>{width:.1f}</width></LineStyle></Style>")
    body = "".join(
        f"<Folder><name>{escape(f.name)}</name>" + "".join(_placemark(p) for p in f.placemarks) + "</Folder>"
        for f in folders if f.placemarks
    )
    doc = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           f"<name>{escape(name)}</name><description>{escape(attribution.SHORT)}</description>"
           f"{''.join(styles)}{body}</Document></kml>\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        ziputil.writestr(z, "doc.kml", doc)
        for icon in sorted(used_icons):
            src = _find(icons_dir, icon)
            if src.exists():
                ziputil.writefile(z, src, f"files/{icon}")
    tmp.replace(path)


def write_network_link(path: Path, name: str, href: str, refresh_s: int) -> None:
    doc = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<kml xmlns="http://www.opengis.net/kml/2.2"><NetworkLink>'
           f"<name>{escape(name)}</name><refreshVisibility>0</refreshVisibility>"
           f"<Link><href>{escape(href)}</href><refreshMode>onInterval</refreshMode>"
           f"<refreshInterval>{int(refresh_s)}</refreshInterval></Link>"
           "</NetworkLink></kml>\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")


def write_link_collection(path: Path, name: str, sections: list[tuple[str, bool, list[tuple[str, str]]]],
                          refresh_s: int) -> None:
    """One KML file with a folder per section and a NetworkLink per area.

    sections: [(folder name, visible, [(area name, KMZ href)])]. A link whose
    href is a list [(name, href)] is a subfolder of links. With visible=False
    the links are off by default and the user turns on the areas they need
    (whether the client defers fetching depends on the client).
    """
    def link(n: str, href: str, vis: int) -> str:
        return (f"<NetworkLink><name>{escape(n)}</name><visibility>{vis}</visibility>"
                f"<refreshVisibility>0</refreshVisibility>"
                f"<Link><href>{escape(href)}</href><refreshMode>onInterval</refreshMode>"
                f"<refreshInterval>{int(refresh_s)}</refreshInterval></Link></NetworkLink>")

    def folder(n: str, links: list, vis: int) -> str:
        return (f"<Folder><name>{escape(n)}</name><visibility>{vis}</visibility>"
                + "".join(folder(ln, h, vis) if isinstance(h, list) else link(ln, h, vis) for ln, h in links)
                + "</Folder>")

    body = [folder(name_, links, 1 if visible else 0) for name_, visible, links in sections]
    doc = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           f"<name>{escape(name)}</name><description>{escape(attribution.SHORT)}</description>"
           + "".join(body) + "</Document></kml>\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")


def _find(dirs, name: str) -> Path:
    """First directory containing the icon (a Path or a list of Paths)."""
    for d in (dirs if isinstance(dirs, (list, tuple)) else [dirs]):
        if (Path(d) / name).exists():
            return Path(d) / name
    return Path(dirs[0] if isinstance(dirs, (list, tuple)) else dirs) / name

"""GPX 1.1 -reitit (<rte>), jotka ATAK voi muuntaa navigoitaviksi reiteiksi.

Korkeutta (<ele>) ei kirjoiteta.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from ..geo import Line

HEADER = ('<?xml version="1.0" encoding="UTF-8"?>\n'
          '<gpx version="1.1" creator="python-lipas2tak-tool" '
          'xmlns="http://www.topografix.com/GPX/1/1">\n')


def route_gpx(name: str, desc: str, lines: list[Line], link: str = "") -> str:
    parts = [HEADER, f"<metadata><name>{escape(name)}</name>"]
    if link:
        parts.append(f'<link href="{escape(link)}"/>')
    parts.append("</metadata>\n")
    for i, line in enumerate(lines, 1):
        rname = name if len(lines) == 1 else f"{name} ({i}/{len(lines)})"
        parts.append(f"<rte><name>{escape(rname)}</name><desc>{escape(desc)}</desc>\n")
        parts.extend(f'<rtept lat="{lat:.6f}" lon="{lon:.6f}"/>\n' for lon, lat in line)
        parts.append("</rte>\n")
    parts.append("</gpx>\n")
    return "".join(parts)


def write_zip(path: Path, files: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files:
            z.writestr(name, content)
    tmp.replace(path)

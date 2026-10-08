"""CoT XML: markers (a-u-G + usericon), routes (b-m-r) and drawn lines (u-d-f).

The structure is derived from data packages exported by ATAK 5.8. Altitude is
not written: ATAK clamps the items to its own elevation model.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import quoteattr, escape

from ..geo import Line

HAE_UNKNOWN = "9999999.0"


def argb_int(hex_rgb: str, alpha: int = 255) -> int:
    """'#RRGGBB' -> ATAK's signed ARGB integer."""
    h = hex_rgb.lstrip("#")
    v = (alpha << 24) | int(h, 16)
    return v - (1 << 32) if v >= (1 << 31) else v


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _times(now: datetime, stale_days: int) -> str:
    return (f"time='{_ts(now)}' start='{_ts(now)}' "
            f"stale='{_ts(now + timedelta(days=stale_days))}'")


def _fmt(v: float) -> str:
    return f"{v:.6f}".rstrip("0").rstrip(".")


def marker(uid: str, cot_type: str, lat: float, lon: float, callsign: str, remarks: str,
           iconsetpath: str | None, now: datetime | None = None, stale_days: int = 365) -> str:
    now = now or datetime.now(timezone.utc)
    icon = f"<usericon iconsetpath={quoteattr(iconsetpath)}/>" if iconsetpath else ""
    return (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        f"<event version='2.0' uid={quoteattr(uid)} type={quoteattr(cot_type)} {_times(now, stale_days)} "
        "how='h-g-i-g-o' access='Undefined'>"
        f"<point lat='{_fmt(lat)}' lon='{_fmt(lon)}' hae='{HAE_UNKNOWN}' ce='{HAE_UNKNOWN}' le='{HAE_UNKNOWN}'/>"
        "<detail><status readiness='true'/><archive/>"
        f"<contact callsign={quoteattr(callsign)}/>{icon}"
        f"<remarks>{escape(remarks)}</remarks>"
        "<color argb='-1'/></detail></event>"
    )


def polyline(uid: str, line: Line, callsign: str, remarks: str, color_hex: str,
             stroke_weight: float = 4.0, now: datetime | None = None, stale_days: int = 365,
             link_hae: bool = False) -> str:
    """Drawn line (u-d-f). `line` is [(lon, lat), ...]."""
    now = now or datetime.now(timezone.utc)
    argb = argb_int(color_hex)
    suffix = f",{HAE_UNKNOWN}" if link_hae else ""
    links = "".join(f"<link point='{_fmt(lat)},{_fmt(lon)}{suffix}'/>" for lon, lat in line)
    lon0, lat0 = line[0]
    return (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        f"<event version='2.0' uid={quoteattr(uid)} type='u-d-f' {_times(now, stale_days)} "
        "how='h-e' access='Undefined'>"
        f"<point lat='{_fmt(lat0)}' lon='{_fmt(lon0)}' hae='{HAE_UNKNOWN}' ce='{HAE_UNKNOWN}' le='{HAE_UNKNOWN}'/>"
        f"<detail>{links}"
        f"<strokeColor value='{argb}'/><strokeWeight value='{stroke_weight:.1f}'/>"
        "<strokeStyle value='solid'/>"
        # Transparent fill: otherwise ATAK fills closed (loop) lines
        "<fillColor value='0'/>"
        f"<contact callsign={quoteattr(callsign)}/>"
        f"<remarks>{escape(remarks)}</remarks>"
        "<archive/><labels_on value='false'/>"
        f"<color value='{argb}'/></detail></event>"
    )


def route(uid: str, line: Line, callsign: str, remarks: str, color_hex: str,
          start_name: str, end_name: str, stroke_weight: float = 3.0,
          method: str = "Walking", route_kind: str = "On Foot",
          now: datetime | None = None, stale_days: int = 365,
          waypoints: dict[int, tuple[str, str]] | None = None) -> str:
    """Navigable ATAK route (b-m-r).

    `waypoints`: {vertex index: (name, description)} – rest stops along the
    route as named waypoints (b-m-p-w) that ATAK navigation refers to.

    The structure mirrors ATAK 5.8's own export: the route's own point is 0,0;
    route points are <link> elements, the first and last being named waypoints
    (b-m-p-w) and the rest check points (b-m-p-c). ATAK computes navigation cues
    itself. Point UIDs are deterministic (`<uid>-p<n>`) so an update replaces
    the previous route.
    """
    now = now or datetime.now(timezone.utc)
    argb = argb_int(color_hex)
    links = []
    last = len(line) - 1
    for i, (lon, lat) in enumerate(line):
        if i == 0:
            typ, cs = "b-m-p-w", start_name
        elif i == last:
            typ, cs = "b-m-p-w", end_name
        elif waypoints and i in waypoints:
            typ, cs = "b-m-p-w", waypoints[i][0]
        else:
            typ, cs = "b-m-p-c", ""
        rem = waypoints[i][1] if waypoints and i in waypoints else ""
        links.append(f"<link uid={quoteattr(f'{uid}-p{i}')} callsign={quoteattr(cs)} type='{typ}' "
                     f"point='{_fmt(lat)},{_fmt(lon)}' remarks={quoteattr(rem)} relation='c'/>")
    return (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        f"<event version='2.0' uid={quoteattr(uid)} type='b-m-r' {_times(now, stale_days)} "
        "how='h-e' access='Undefined'>"
        f"<point lat='0.0' lon='0.0' hae='{HAE_UNKNOWN}' ce='{HAE_UNKNOWN}' le='{HAE_UNKNOWN}'/>"
        f"<detail>{''.join(links)}"
        f"<link_attr planningmethod='Infil' color='{argb}' method={quoteattr(method)} prefix='CP' "
        f"style='0' type={quoteattr(route_kind)} stroke='{int(stroke_weight)}' direction='Infil' "
        "routetype='Primary' order='Ascending Check Points'/>"
        "<__routeinfo><__navcues/></__routeinfo>"
        "<labels_on value='false'/>"
        f"<strokeColor value='{argb}'/><strokeWeight value='{stroke_weight:.1f}'/>"
        "<strokeStyle value='solid'/>"
        f"<contact callsign={quoteattr(callsign)}/>"
        f"<remarks>{escape(remarks)}</remarks>"
        f"<archive/><color value='{argb}'/></detail></event>"
    )

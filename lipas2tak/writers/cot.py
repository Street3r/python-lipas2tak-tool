"""CoT-XML: merkit (a-u-G + usericon) ja reittiviivat (u-d-f).

Rakenne on johdettu ATAK 5.8:lla tehdystä esimerkkidatapaketista
(docs/atak-esimerkit/). Korkeutta ei kirjoiteta: ATAK sitoo kohteet
omaan korkeusmalliinsa (päätös 7.10.2026).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import quoteattr, escape

from ..geo import Line

HAE_UNKNOWN = "9999999.0"


def argb_int(hex_rgb: str, alpha: int = 255) -> int:
    """'#RRGGBB' -> ATAKin etumerkillinen ARGB-kokonaisluku."""
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
    """Reittiviiva (u-d-f). `line` on [(lon, lat), ...]."""
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
        # Läpinäkyvä täyttö: muuten ATAK täyttää umpinaiset (silmukka-)reitit
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
    """Navigoitava ATAK-reitti (b-m-r).

    `waypoints`: {solmuindeksi: (nimi, kuvaus)} – reitin varren taukopaikat
    nimettyinä reittipisteinä (b-m-p-w), joihin ATAKin navigointi viittaa.

    Rakenne on kopioitu ATAK 5.8:n omasta viennistä (Iivaara-esimerkki):
    reitin oma piste on 0,0; reittipisteet ovat <link>-elementtejä, joista
    ensimmäinen ja viimeinen ovat nimettyjä reittipisteitä (b-m-p-w) ja
    välissä tarkistuspisteitä (b-m-p-c). Navigointiohjeet ATAK laskee itse.
    Pisteiden UID:t ovat deterministisiä (`<uid>-p<n>`), jotta päivitys
    korvaa vanhan reitin.
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

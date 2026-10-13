"""Mission package that adds an auto-refreshing KML/KMZ link to ATAK.

ATAK imports a plain .kml/.kmz URL (QR code, tak:// link) as a one-off copy;
a refreshing network link is otherwise added only by hand (Import → KML Link).
ATAK's own "send" of a Network Resource is a mission package holding one
`b-i-r-r` CoT event with a <RemoteResource>; importing that package creates the
refreshing link directly, so it can be opened with a QR code or a button.

The structure mirrors ATAK's own export (ATAK 5.x, tested). Output is
deterministic: fixed UIDs (from the URL) and fixed timestamps.
"""
from __future__ import annotations

import uuid
import zipfile
from pathlib import Path

from . import ziputil
from .xmltext import quoteattr

TIME = "2026-01-01T00:00:00.000Z"
STALE = "2036-01-01T00:00:00.000Z"


def write(path: Path, name: str, url: str, refresh_s: int = 86400,
          point: tuple[float, float] = (64.0, 26.0)) -> str:
    """Write the package; returns its UID. `point` is (lat, lon)."""
    res_type = "KMZ" if url.lower().endswith(".kmz") else "KML"
    event_uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"lipas2tak-remote-resource:{url}"))
    pkg_uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"lipas2tak-remote-resource-pkg:{url}\0{name}\0{refresh_s}"))
    folder = event_uid.replace("-", "")
    entry = f"{folder}/{folder}.cot"
    lat, lon = point
    cot = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        f"<event version='2.0' uid={quoteattr(event_uid)} type='b-i-r-r' time='{TIME}' start='{TIME}' "
        f"stale='{STALE}' how='h-g' access='Undefined'>"
        f"<point lat='{lat:.6f}' lon='{lon:.6f}' hae='9999999.0' ce='9999999.0' le='9999999.0' />"
        f"<detail><contact callsign={quoteattr(name)}/><RemoteResources>"
        f"<RemoteResource name={quoteattr(name)} refreshSeconds='{int(refresh_s)}' type='{res_type}' "
        f"url={quoteattr(url)} deleteOnExit='false'/>"
        "</RemoteResources></detail></event>"
    )
    manifest = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<MissionPackageManifest version="2">\n'
        "   <Configuration>\n"
        f'      <Parameter name="uid" value="{pkg_uid}"/>\n'
        f"      <Parameter name=\"name\" value={quoteattr(name)}/>\n"
        '      <Parameter name="onReceiveImport" value="true"/>\n'
        # The package only carries the link; ATAK's own export deletes it after import
        '      <Parameter name="onReceiveDelete" value="true"/>\n'
        "   </Configuration>\n"
        "   <Contents>\n"
        f'      <Content ignore="false" zipEntry="{entry}">\n'
        f"         <Parameter name=\"name\" value={quoteattr(name)}/>\n"
        '         <Parameter name="contentType" value="Remote Resource"/>\n'
        "      </Content>\n"
        "   </Contents>\n"
        "</MissionPackageManifest>\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w") as z:
        ziputil.writestr(z, "MANIFEST/manifest.xml", manifest)
        ziputil.writestr(z, entry, cot)
    tmp.replace(path)
    return pkg_uid

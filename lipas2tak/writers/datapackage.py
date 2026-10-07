"""ATAK Mission Package v2 (datapaketti, .zip).

Rakenne (ATAKin oma vienti):
    MANIFEST/manifest.xml
    <uid>/<uid>.cot
Paketin UID on deterministinen (uuid5 nimestä), joten uusi versio
korvaa vanhan ATAKissa eikä synny rinnakkaisia paketteja.
"""
from __future__ import annotations

import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

NAMESPACE = uuid.UUID("6b1c2b9e-1f55-4d0e-9c4a-6c2a3c5d2a10")


def package_uid(key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, key))


def write(path: Path, name: str, key: str, items: list[tuple[str, str, str]],
          extra_files: list[tuple[str, bytes]] | None = None) -> None:
    """items: [(uid, nimi, cot_xml)], extra_files: [(zip-polku, sisältö)]"""
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = []
    for uid, title, _ in items:
        contents.append(
            f'      <Content ignore="false" zipEntry="{uid}/{uid}.cot">\n'
            f'         <Parameter name="uid" value={quoteattr(uid)}/>\n'
            f'         <Parameter name="name" value={quoteattr(title)}/>\n'
            f"      </Content>"
        )
    for zpath, _ in extra_files or []:
        contents.append(f'      <Content ignore="false" zipEntry={quoteattr(zpath)}/>')
    manifest = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<MissionPackageManifest version="2">\n'
        "   <Configuration>\n"
        f'      <Parameter name="uid" value="{package_uid(key)}"/>\n'
        f"      <Parameter name=\"name\" value={quoteattr(name)}/>\n"
        '      <Parameter name="onReceiveDelete" value="true"/>\n'
        "   </Configuration>\n"
        "   <Contents>\n" + "\n".join(contents) + "\n   </Contents>\n"
        "</MissionPackageManifest>\n"
    )
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("MANIFEST/manifest.xml", manifest)
        for uid, _, xml in items:
            z.writestr(f"{uid}/{uid}.cot", xml)
        for zpath, data in extra_files or []:
            z.writestr(zpath, data)
    tmp.replace(path)

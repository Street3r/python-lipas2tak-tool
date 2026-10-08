"""ATAK Mission Package v2 (data package, .zip).

Layout (as exported by ATAK):
    MANIFEST/manifest.xml
    <uid>/<uid>.cot
The package UID is deterministic (uuid5 of the name), so a new version
replaces the old one in ATAK instead of creating parallel packages.
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
          extra_files: list[tuple[str, bytes]] | None = None,
          remarks: str = "", notice: str = "") -> None:
    """items: [(uid, name, cot_xml)], extra_files: [(zip path, content)].

    `remarks` is shown with the package in ATAK; `notice` is stored as
    ATTRIBUTION.txt, which ATAK does not import (ignore="true").
    """
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
    if notice:
        contents.append('      <Content ignore="true" zipEntry="ATTRIBUTION.txt"/>')
    remarks_param = f'      <Parameter name="remarks" value={quoteattr(remarks)}/>\n' if remarks else ""
    manifest = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<MissionPackageManifest version="2">\n'
        "   <Configuration>\n"
        f'      <Parameter name="uid" value="{package_uid(key)}"/>\n'
        f"      <Parameter name=\"name\" value={quoteattr(name)}/>\n"
        '      <Parameter name="onReceiveDelete" value="true"/>\n'
        + remarks_param +
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
        if notice:
            z.writestr("ATTRIBUTION.txt", notice)
    tmp.replace(path)

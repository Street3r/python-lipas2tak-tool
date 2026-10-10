"""ATAK Mission Package v2 (data package, .zip).

Layout (as exported by ATAK):
    MANIFEST/manifest.xml
    <uid>/<uid>.cot
The package UID is derived from the area key AND the content: TAK clients
skip a package whose UID they have already imported, so the UID changes
whenever anything in the package changes, and stays the same when nothing
did (a re-import of identical content is skipped). CoT items keep their own
stable UIDs, so a new version updates the existing markers and routes
instead of duplicating them.
"""
from __future__ import annotations

import hashlib
import uuid
import zipfile
from pathlib import Path
from .xmltext import quoteattr
from . import ziputil

NAMESPACE = uuid.UUID("6b1c2b9e-1f55-4d0e-9c4a-6c2a3c5d2a10")


def content_hash(items: list[tuple[str, str, str]], extra_files=None, remarks: str = "",
                 notice: str = "") -> str:
    h = hashlib.sha256()
    for uid, title, xml in sorted(items):
        h.update(f"{uid}\0{title}\0{xml}\0".encode())
    for zpath, data in sorted(extra_files or []):
        h.update(zpath.encode() + b"\0" + (data if isinstance(data, bytes) else data.encode()) + b"\0")
    h.update(remarks.encode() + b"\0" + notice.encode())
    return h.hexdigest()


def package_uid(key: str, digest: str = "") -> str:
    """uuid5 of the area key and the content digest."""
    return str(uuid.uuid5(NAMESPACE, f"{key}|{digest}" if digest else key))


def write(path: Path, name: str, key: str, items: list[tuple[str, str, str]],
          extra_files: list[tuple[str, bytes]] | None = None,
          remarks: str = "", notice: str = "", on_receive_delete: bool = False) -> str:
    """items: [(uid, name, cot_xml)], extra_files: [(zip path, content)].

    `remarks` is shown with the package in ATAK; `notice` is stored as
    ATTRIBUTION.txt, which ATAK does not import (ignore="true").
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # onReceiveDelete=false keeps the package listed in ATAK's Data Packages, so its
    # contents can be hidden or removed together. Part of the UID so a change re-imports.
    flag = "true" if on_receive_delete else "false"
    pkg_uid = package_uid(key, content_hash(items, extra_files, f"{name}\0{remarks}\0{flag}", notice))
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
        f'      <Parameter name="uid" value="{pkg_uid}"/>\n'
        f"      <Parameter name=\"name\" value={quoteattr(name)}/>\n"
        f'      <Parameter name="onReceiveDelete" value="{flag}"/>\n'
        + remarks_param +
        "   </Configuration>\n"
        "   <Contents>\n" + "\n".join(contents) + "\n   </Contents>\n"
        "</MissionPackageManifest>\n"
    )
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        ziputil.writestr(z, "MANIFEST/manifest.xml", manifest)
        for uid, _, xml in items:
            ziputil.writestr(z, f"{uid}/{uid}.cot", xml)
        for zpath, data in extra_files or []:
            ziputil.writestr(z, zpath, data)
        if notice:
            ziputil.writestr(z, "ATTRIBUTION.txt", notice)
    tmp.replace(path)
    return pkg_uid

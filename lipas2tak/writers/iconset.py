"""ATAK icon set (iconset .zip).

Layout (ATAK-CIV UserIconSet/UserIcon):
    iconset.xml          <iconset name uid version [defaultGroup skipResize ...]>
                           <icon name="icon.png" type2525b="a-u-G"/>
    <group>/<icon>.png   group = directory in the zip (not in the XML)
CoT markers refer to an icon with the path `<iconset-uid>/<group>/<icon>.png`.
The iconset UID is fixed so that swapping the icons does not break markers
that have already been shared: just install the new zip.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr
from . import ziputil

ICONSET_UID = "3c1f9a52-8d0e-4c41-9b0a-1a2d5e7f4b61"
ICONSET_GROUP = "Retkeily"
ICONSET_NAME = "Lipas retkeily"


def iconsetpath(icon: str) -> str:
    return f"{ICONSET_UID}/{ICONSET_GROUP}/{icon}"


def write(path: Path, icons_dir, icons: list[str], cot_type: str = "a-u-G") -> None:
    entries = "\n".join(f"  <icon name={quoteattr(i)} type2525b={quoteattr(cot_type)}/>" for i in sorted(set(icons)))
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        # Attribute names follow ATAK's UserIconSet class (camelCase)
        f'<iconset version="1" name="{ICONSET_NAME}" defaultGroup="{ICONSET_GROUP}" '
        f'uid="{ICONSET_UID}" skipResize="false">\n{entries}\n</iconset>\n'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        ziputil.writestr(z, "iconset.xml", xml)
        for i in sorted(set(icons)):
            src = _find(icons_dir, i)
            if src.exists():
                ziputil.writefile(z, src, f"{ICONSET_GROUP}/{i}")
    tmp.replace(path)


def _find(dirs, name: str) -> Path:
    """First directory containing the icon (a Path or a list of Paths)."""
    for d in (dirs if isinstance(dirs, (list, tuple)) else [dirs]):
        if (Path(d) / name).exists():
            return Path(d) / name
    return Path(dirs[0] if isinstance(dirs, (list, tuple)) else dirs) / name

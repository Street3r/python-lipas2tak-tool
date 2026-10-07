"""ATAK-kuvakesarja (iconset .zip).

Rakenne:
    iconset.xml
    <ryhmä>/<kuvake>.png
CoT-merkit viittaavat kuvakkeeseen polulla `<iconset-uid>/<ryhmä>/<kuvake>.png`.
Iconsetin UID on kiinteä, jotta kuvakkeiden vaihto (esim. Metsähallituksen
luvan jälkeen) ei riko jo jaettuja merkkejä: asennetaan vain uusi zip.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

ICONSET_UID = "3c1f9a52-8d0e-4c41-9b0a-1a2d5e7f4b61"
ICONSET_GROUP = "Retkeily"
ICONSET_NAME = "Lipas retkeily"


def iconsetpath(icon: str) -> str:
    return f"{ICONSET_UID}/{ICONSET_GROUP}/{icon}"


def write(path: Path, icons_dir: Path, icons: list[str], cot_type: str = "a-u-G") -> None:
    entries = "\n".join(f"  <icon name={quoteattr(i)} type2525b={quoteattr(cot_type)}/>" for i in sorted(set(icons)))
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<iconset version="1" name="{ICONSET_NAME}" default_group="{ICONSET_GROUP}" '
        f'uid="{ICONSET_UID}" skip_resize="false">\n{entries}\n</iconset>\n'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("iconset.xml", xml)
        for i in sorted(set(icons)):
            src = icons_dir / i
            if src.exists():
                z.write(src, f"{ICONSET_GROUP}/{i}")
    tmp.replace(path)

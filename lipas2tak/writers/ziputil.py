"""Deterministic zip writing: fixed timestamps and permissions, so unchanged
content produces byte-identical files (no spurious changes when publishing)."""
from __future__ import annotations

import zipfile
from pathlib import Path

FIXED_DATE = (2026, 1, 1, 0, 0, 0)


def writestr(z: zipfile.ZipFile, name: str, data: str | bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=FIXED_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    z.writestr(info, data)


def writefile(z: zipfile.ZipFile, src: Path, name: str) -> None:
    writestr(z, name, Path(src).read_bytes())

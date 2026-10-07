"""Asetusten lataus (config.yaml + types.yaml) ja ympäristömuuttujat."""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent

_ENV_OVERRIDES = {
    "LIPAS2TAK_PUBLIC_BASE_URL": ("public_base_url",),
    "LIPAS2TAK_OUTPUT_DIR": ("paths", "output"),
    "LIPAS2TAK_CACHE_DIR": ("paths", "cache"),
    "LIPAS2TAK_ICONS_DIR": ("paths", "icons"),
    "LIPAS2TAK_OVERPASS_URL": ("sources", "osm", "overpass_url"),
}


def slugify(text: str) -> str:
    """Hashtag-/tiedostonimikelpoinen tunniste: a-z0-9 ja väliviiva pois.

    ä→a, ö→o, å→a (ATAKin hashtag-haun varmuuden vuoksi vain ASCII).
    """
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^a-z0-9]+", "", t)
    return t


def file_slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


@dataclass
class Kind:
    key: str
    label: dict
    tag: dict
    group: str
    icon: str | None
    cot_type: str
    color: str | None
    sources: dict
    enabled: bool = True

    @property
    def is_route(self) -> bool:
        return self.group == "reitit"

    @property
    def name_regex(self):
        rx = (self.sources.get("lipas") or {}).get("name_regex")
        return re.compile(rx, re.I) if rx else None


@dataclass
class Settings:
    raw: dict
    kinds: dict[str, Kind]
    groups: dict[str, dict]
    root: Path
    area_names: dict[str, dict[str, str]] = None  # type: ignore[assignment]

    def get(self, *path: str, default: Any = None) -> Any:
        cur: Any = self.raw
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur

    def path(self, key: str) -> Path:
        p = Path(self.get("paths", key))
        return p if p.is_absolute() else self.root / p

    @property
    def languages(self) -> list[str]:
        return list(self.get("languages", default=["fi"]))

    def enabled_kinds(self) -> list[Kind]:
        return [k for k in self.kinds.values() if k.enabled]


def _set(d: dict, path: tuple[str, ...], value: Any) -> None:
    for p in path[:-1]:
        d = d.setdefault(p, {})
    d[path[-1]] = value


def load_settings(config_path: str | Path | None = None, types_path: str | Path | None = None,
                  root: Path | None = None) -> Settings:
    config_path = Path(config_path or os.environ.get("LIPAS2TAK_CONFIG") or (root or ROOT) / "config" / "config.yaml")
    types_path = Path(types_path or os.environ.get("LIPAS2TAK_TYPES") or config_path.parent / "types.yaml")
    # Suhteelliset polut (icons, data) ratkaistaan config-hakemiston yläkansiosta
    root = root or config_path.resolve().parent.parent
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    for env, path in _ENV_OVERRIDES.items():
        if os.environ.get(env):
            _set(raw, path, os.environ[env])
    t = yaml.safe_load(types_path.read_text(encoding="utf-8"))
    kinds = {}
    for key, k in t["kinds"].items():
        kinds[key] = Kind(
            key=key,
            label=k["label"],
            tag=k["tag"],
            group=k["group"],
            icon=k.get("icon"),
            cot_type=k.get("cot_type", "a-u-G"),
            color=k.get("color"),
            sources=k.get("sources") or {},
            enabled=k.get("enabled", True),
        )
    names_path = config_path.parent / "area_names.yaml"
    names = yaml.safe_load(names_path.read_text(encoding="utf-8")) if names_path.exists() else {}
    return Settings(raw=raw, kinds=kinds, groups=t.get("groups", {}), root=root, area_names=names or {})

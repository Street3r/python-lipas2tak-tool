"""Small file helpers: atomic writes and tolerant JSON reads.

State and cache files must survive an interrupted run (container stopped,
disk full). A half-written file would otherwise break every later run.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def write_text_atomic(path: Path, text: str) -> None:
    """Write via a temporary file in the same directory and rename it into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_json_atomic(path: Path, data: Any, **kw) -> None:
    write_text_atomic(path, json.dumps(data, **kw))


def read_json(path: Path, default: Any = None) -> Any:
    """JSON content of `path`; `default` if it is missing or unreadable (logged)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as e:
        log.warning("Ignoring unreadable file %s: %s", path, e)
        return default

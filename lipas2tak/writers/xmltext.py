"""XML escaping that also removes characters XML 1.0 does not allow.

Source texts sometimes contain control characters (e.g. U+0002 left over from
soft hyphens in Lipas descriptions). A single one makes the whole KML/CoT file
invalid, and ATAK then shows nothing from it.
"""
from __future__ import annotations

import re
from xml.sax import saxutils

_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f\ud800-\udfff￾￿]")


def clean(text: str) -> str:
    return _INVALID.sub("", text)


def escape(text: str, entities: dict | None = None) -> str:
    return saxutils.escape(clean(text), entities or {})


def quoteattr(text: str, entities: dict | None = None) -> str:
    return saxutils.quoteattr(clean(text), entities or {})

"""Lipas REST API v2: /sports-sites ja /lois.

Rajapinta: https://api.lipas.fi/v2 (avoin, ei tunnistautumista).
Monivalintaparametrit (type-codes, statuses ...) lähetetään toistettuina
query-parametreina (`type-codes=301&type-codes=302`).
"""
from __future__ import annotations

import logging
from typing import Iterator

from .http import CachedClient

log = logging.getLogger(__name__)


class LipasClient:
    def __init__(self, client: CachedClient, base_url: str, page_size: int = 100):
        self.http = client
        self.base_url = base_url.rstrip("/")
        self.page_size = min(100, page_size)

    def _paged(self, path: str, params: dict) -> Iterator[dict]:
        page = 1
        while True:
            p = dict(params, page=page, **{"page-size": self.page_size})
            data = self.http.get_json(f"{self.base_url}{path}", params=p)
            items = data.get("items") or []
            yield from items
            pag = data.get("pagination") or {}
            total_pages = pag.get("total-pages") or 0
            if page >= total_pages or not items:
                break
            page += 1

    def sports_sites(self, type_codes: list[int], statuses: list[str] | None = None) -> Iterator[dict]:
        """Hakee kaikki kohteet annetuilla tyyppikoodeilla, yksi tyyppi kerrallaan.

        Yksi tyyppi kerrallaan, koska välimuisti ja virhetilanteet ovat silloin
        selkeämpiä ja yksittäisen tyypin uudelleenhaku on halpa.
        """
        for code in sorted(set(type_codes)):
            params: dict = {"type-codes": [code]}
            if statuses:
                params["statuses"] = statuses
            n = 0
            for item in self._paged("/sports-sites", params):
                n += 1
                yield item
            log.info("Lipas tyyppi %s: %d kohdetta", code, n)

    def lois(self, types: list[str], statuses: list[str] | None = None) -> Iterator[dict]:
        for t in sorted(set(types)):
            params: dict = {"types": [t]}
            if statuses:
                params["statuses"] = statuses
            n = 0
            for item in self._paged("/lois", params):
                n += 1
                yield item
            log.info("Lipas LOI %s: %d kohdetta", t, n)

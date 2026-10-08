"""HTTP fetching with an on-disk cache and retries."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

USER_AGENT = "python-lipas2tak-tool (+https://github.com/Street3r/python-lipas2tak-tool)"


class CachedClient:
    def __init__(self, cache_dir: Path, max_age_h: float = 20.0, delay_s: float = 0.3,
                 timeout_s: float = 60.0, retries: int = 4):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_age_s = max_age_h * 3600
        self.delay_s = delay_s
        self.timeout_s = timeout_s
        self.retries = retries
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last = 0.0

    def _key(self, method: str, url: str, params: Any, data: Any) -> Path:
        h = hashlib.sha256(json.dumps([method, url, params, data], sort_keys=True, default=str).encode()).hexdigest()
        return self.cache_dir / f"{h[:32]}.json"

    def get_json(self, url: str, params: Any = None, *, method: str = "GET", data: Any = None,
                 use_cache: bool = True) -> Any:
        path = self._key(method, url, params, data)
        if use_cache and path.exists() and time.time() - path.stat().st_mtime < self.max_age_s:
            return json.loads(path.read_text(encoding="utf-8"))
        wait = max(0.0, self.delay_s - (time.time() - self._last))
        if wait:
            time.sleep(wait)
        last_err: Exception | None = None
        for attempt in range(self.retries):
            try:
                if method == "POST":
                    r = self.session.post(url, params=params, data=data, timeout=self.timeout_s)
                else:
                    r = self.session.get(url, params=params, timeout=self.timeout_s)
                self._last = time.time()
                if r.status_code in (429, 502, 503, 504):
                    raise requests.HTTPError(f"{r.status_code}", response=r)
                r.raise_for_status()
                payload = r.json()
                path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                return payload
            except (requests.RequestException, ValueError) as e:
                last_err = e
                backoff = 2 ** attempt * 2
                log.warning("Request failed (%s), attempt %d/%d, waiting %ss: %s",
                            url, attempt + 1, self.retries, backoff, e)
                time.sleep(backoff)
        raise RuntimeError(f"Request failed: {url}") from last_err

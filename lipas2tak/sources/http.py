"""HTTP fetching with an on-disk cache and retries."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

import requests

log = logging.getLogger(__name__)

USER_AGENT = "python-lipas2tak-tool (+https://github.com/Street3r/python-lipas2tak-tool)"


class CachedClient:
    # Waits between retries; busy servers (e.g. Overpass 504) need longer pauses
    BACKOFF_S = (5, 15, 30, 60, 120)

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
        # (url, age in hours) of every expired cached copy used because a request failed
        self.stale: list[tuple[str, float]] = []

    def _key(self, method: str, url: str, params: Any, data: Any) -> Path:
        h = hashlib.sha256(json.dumps([method, url, params, data], sort_keys=True, default=str).encode()).hexdigest()
        return self.cache_dir / f"{h[:32]}.json"

    def cached(self, url: str, params: Any = None, *, method: str = "GET", data: Any = None,
               quiet: bool = False) -> Any:
        """Last cached response regardless of age, or None (no network request)."""
        path = self._key(method, url, params, data)
        if not path.exists():
            return None
        if not quiet:
            age_h = (time.time() - path.stat().st_mtime) / 3600
            log.warning("Using cached copy of %s from %.0f h ago", url, age_h)
            self.stale.append((url, age_h))
        return json.loads(path.read_text(encoding="utf-8"))

    def get_json(self, url: str, params: Any = None, *, method: str = "GET", data: Any = None,
                 use_cache: bool = True, retries: int | None = None, timeout_s: float | None = None,
                 stale_ok: bool = False, validate: Callable[[Any], None] | None = None,
                 deadline: float | None = None) -> Any:
        """Fetch JSON. With stale_ok, an expired cached copy is returned if every attempt fails.

        validate is called with each response before it is cached; raising ValueError
        rejects the response (it is retried and never overwrites a good cached copy).
        deadline (time.time() value): no new attempt is started after it, and a
        request's timeout is cut so that it ends about then.
        """
        path = self._key(method, url, params, data)
        if use_cache and path.exists() and time.time() - path.stat().st_mtime < self.max_age_s:
            return json.loads(path.read_text(encoding="utf-8"))
        wait = max(0.0, self.delay_s - (time.time() - self._last))
        if wait:
            time.sleep(wait)
        last_err: Exception | None = None
        retries = retries or self.retries
        for attempt in range(retries):
            timeout = timeout_s or self.timeout_s
            if deadline is not None:
                timeout = max(30.0, min(timeout, deadline - time.time()))
            try:
                if method == "POST":
                    r = self.session.post(url, params=params, data=data, timeout=timeout)
                else:
                    r = self.session.get(url, params=params, timeout=timeout)
                self._last = time.time()
                if r.status_code in (429, 502, 503, 504):
                    raise requests.HTTPError(f"{r.status_code}", response=r)
                r.raise_for_status()
                payload = r.json()
                if validate:
                    validate(payload)
                path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                return payload
            except (requests.RequestException, ValueError) as e:
                last_err = e
                backoff = self.BACKOFF_S[min(attempt, len(self.BACKOFF_S) - 1)]
                if attempt + 1 == retries:
                    break
                if deadline is not None and time.time() + backoff >= deadline:
                    log.warning("Request failed (%s), time budget used up: %s", url, e)
                    break
                log.warning("Request failed (%s), attempt %d/%d, retrying in %ss: %s",
                            url, attempt + 1, retries, backoff, e)
                time.sleep(backoff)
        if stale_ok and path.exists():
            age_h = (time.time() - path.stat().st_mtime) / 3600
            log.warning("Request failed (%s): using cached copy from %.0f h ago", url, age_h)
            self.stale.append((url, age_h))
            return json.loads(path.read_text(encoding="utf-8"))
        raise RuntimeError(f"Request failed: {url}") from last_err

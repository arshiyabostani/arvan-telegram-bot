"""Async client for the ArvanCloud CDN API (v4.0).

Design notes
------------
* Security policy lives here, not in the Telegram layer. Read-only mode and the
  domain allowlist are enforced for every call, so a bug in a handler cannot
  bypass them.
* Every path segment is validated and percent-encoded.
* Only GET requests are retried. Retrying a POST or DELETE could repeat a
  change the server already applied.
* Error messages exposed to callers never include raw response bodies.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Iterable
from typing import Any
from urllib.parse import quote

import httpx

from arvan_bot import __version__
from arvan_bot.validation import (
    MAX_PURGE_URLS,
    validate_domain,
    validate_purge_urls,
    validate_record_id,
)

from .errors import (
    ArvanAPIError,
    ArvanAuthError,
    ArvanNetworkError,
    ArvanNotFoundError,
    ArvanRateLimitError,
    DomainNotAllowedError,
    ReadOnlyError,
)

DEFAULT_BASE_URL = "https://napi.arvancloud.ir"
_API_PREFIX = ("cdn", "4.0")
_RETRY_STATUSES = frozenset({429, 502, 503, 504})
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MAX_DETAIL = 200


class ArvanClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        read_only: bool = False,
        allowed_domains: Iterable[str] = (),
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("base_url must use https")
        self._read_only = read_only
        self._allowed = frozenset(allowed_domains)
        self._max_retries = max_retries
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Apikey {api_key}",
                "Accept": "application/json",
                "User-Agent": f"arvan-telegram-bot/{__version__}",
            },
            timeout=httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            follow_redirects=False,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ policy
    def ensure_writable(self) -> None:
        if self._read_only:
            raise ReadOnlyError()

    def _domain(self, domain: str) -> str:
        name = validate_domain(domain)
        if self._allowed and name not in self._allowed:
            raise DomainNotAllowedError()
        return name

    # --------------------------------------------------------------- transport
    async def _request(
        self,
        method: str,
        *segments: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = "/" + "/".join(quote(s, safe="") for s in (*_API_PREFIX, *segments))
        attempts = 1 + (self._max_retries if method == "GET" else 0)
        for attempt in range(attempts):
            last = attempt + 1 == attempts
            try:
                resp = await self._http.request(method, path, params=params, json=body)
            except httpx.TransportError as exc:
                if last:
                    raise ArvanNetworkError("could not reach the Arvan API") from exc
                await self._sleep(0.5 * 2**attempt)
                continue
            if resp.status_code in _RETRY_STATUSES and not last:
                await self._sleep(self._retry_delay(resp, attempt))
                continue
            return self._handle(resp)
        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    def _retry_delay(resp: httpx.Response, attempt: int) -> float:
        try:
            return min(float(resp.headers["Retry-After"]), 5.0)
        except (KeyError, ValueError):
            return 0.5 * 2**attempt

    @staticmethod
    def _json(resp: httpx.Response) -> dict[str, Any]:
        try:
            data = resp.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    @classmethod
    def _handle(cls, resp: httpx.Response) -> dict[str, Any]:
        data = cls._json(resp)
        status = resp.status_code
        if 200 <= status < 300:
            return data
        if status in (401, 403):
            raise ArvanAuthError(status, f"HTTP {status}: API key rejected or lacks permission")
        detail = cls._detail(data)
        if status == 404:
            raise ArvanNotFoundError(status, f"HTTP 404: {detail or 'not found'}")
        if status == 429:
            raise ArvanRateLimitError(status, "HTTP 429: rate limited, try again shortly")
        raise ArvanAPIError(status, f"HTTP {status}: {detail or 'request failed'}")

    @staticmethod
    def _detail(data: dict[str, Any]) -> str:
        parts: list[str] = []
        if isinstance(data.get("message"), str):
            parts.append(data["message"])
        errors = data.get("errors")
        if isinstance(errors, dict):
            for field, msgs in list(errors.items())[:3]:
                first = msgs[0] if isinstance(msgs, list) and msgs else msgs
                parts.append(f"{field}: {first}")
        text = _CONTROL_CHARS.sub(" ", "; ".join(str(p) for p in parts))
        return text[:_MAX_DETAIL]

    async def _paginate(self, *segments: str, per_page: int = 100, max_pages: int = 20) -> list[dict]:
        items: list[dict] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            data = await self._request("GET", *segments, params={"per_page": per_page, "page": page})
            batch = data.get("data")
            if not isinstance(batch, list):
                break
            fresh = 0
            for item in batch:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("id") or json.dumps(item, sort_keys=True))
                if key not in seen:
                    seen.add(key)
                    items.append(item)
                    fresh += 1
            meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
            last_page = meta.get("last_page")
            if fresh == 0 or len(batch) < per_page or (isinstance(last_page, int) and page >= last_page):
                break
        return items

    # ----------------------------------------------------------------- domains
    async def list_domains(self) -> list[dict]:
        items = await self._paginate("domains")
        return [d for d in items if isinstance(d.get("domain"), str) and self._visible(d["domain"])]

    def _visible(self, name: str) -> bool:
        return not self._allowed or name.lower() in self._allowed

    async def get_domain(self, domain: str) -> dict:
        data = await self._request("GET", "domains", self._domain(domain))
        return data.get("data", {}) if isinstance(data.get("data"), dict) else {}

    # --------------------------------------------------------------------- DNS
    async def list_records(self, domain: str) -> list[dict]:
        return await self._paginate("domains", self._domain(domain), "dns-records")

    async def get_record(self, domain: str, record_id: str) -> dict:
        data = await self._request("GET", "domains", self._domain(domain), "dns-records", validate_record_id(record_id))
        return data.get("data", {}) if isinstance(data.get("data"), dict) else {}

    async def create_record(self, domain: str, payload: dict[str, Any]) -> dict:
        self.ensure_writable()
        data = await self._request("POST", "domains", self._domain(domain), "dns-records", body=payload)
        return data.get("data", {}) if isinstance(data.get("data"), dict) else {}

    async def delete_record(self, domain: str, record_id: str) -> None:
        self.ensure_writable()
        await self._request("DELETE", "domains", self._domain(domain), "dns-records", validate_record_id(record_id))

    async def set_cloud(self, domain: str, record_id: str, enabled: bool) -> None:
        self.ensure_writable()
        await self._request(
            "PUT",
            "domains",
            self._domain(domain),
            "dns-records",
            validate_record_id(record_id),
            "cloud",
            body={"cloud": bool(enabled)},
        )

    # ------------------------------------------------------------------- cache
    async def purge_all(self, domain: str) -> str:
        self.ensure_writable()
        data = await self._request("POST", "domains", self._domain(domain), "caching", "purge", body={"purge": "all"})
        return str(data.get("message", ""))

    async def purge_urls(self, domain: str, urls: list[str]) -> str:
        self.ensure_writable()
        name = self._domain(domain)
        checked = validate_purge_urls("\n".join(urls), name, max_urls=MAX_PURGE_URLS)
        data = await self._request(
            "POST",
            "domains",
            name,
            "caching",
            "purge",
            body={"purge": "individual", "purge_urls": checked},
        )
        return str(data.get("message", ""))

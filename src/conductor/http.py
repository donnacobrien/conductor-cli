"""Thin REST client for the Arize v2 API.

Grounded directly against the OpenAPI spec at https://api.arize.com/v2/spec.yaml
(not the `arize` SDK, which doesn't expose everything we need — e.g. `is_private`
on spaces). Bearer auth, cursor pagination, 429/Retry-After backoff.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx

DEFAULT_LIST_LIMIT = 100
MAX_RETRIES = 5


@dataclass
class ArizeAPIError(Exception):
    """Raised for any non-2xx response, carrying enough context to say
    *which* resource conductor was working on when the call failed."""

    method: str
    path: str
    status_code: int
    body: Any
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        ctx = ", ".join(f"{k}={v}" for k, v in self.context.items())
        ctx_str = f" [{ctx}]" if ctx else ""
        return (
            f"{self.method} {self.path} -> {self.status_code}{ctx_str}: {self.body!r}"
        )


class ArizeClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ArizeClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- low-level request with 429 backoff -------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        attempt = 0
        while True:
            resp = self._client.request(method, path, params=params, json=json)
            if resp.status_code == 429 and attempt < MAX_RETRIES:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2**attempt, 30)
                time.sleep(delay)
                attempt += 1
                continue
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                except ValueError:
                    body = resp.text
                raise ArizeAPIError(
                    method=method,
                    path=path,
                    status_code=resp.status_code,
                    body=body,
                    context=context or {},
                )
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()

    def get(self, path: str, *, params: dict[str, Any] | None = None, context=None) -> Any:
        return self.request("GET", path, params=params, context=context)

    def post(self, path: str, *, json: dict[str, Any] | None = None, context=None) -> Any:
        return self.request("POST", path, json=json, context=context)

    def patch(self, path: str, *, json: dict[str, Any] | None = None, context=None) -> Any:
        return self.request("PATCH", path, json=json, context=context)

    def delete(self, path: str, *, params: dict[str, Any] | None = None, context=None) -> Any:
        return self.request("DELETE", path, params=params, context=context)

    # -- cursor pagination --------------------------------------------------

    def paginate(
        self,
        path: str,
        *,
        item_key: str,
        params: dict[str, Any] | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
        context: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield every item across all pages of a `list_*` endpoint.

        Assumes the standard response shape: `{<item_key>: [...], "pagination":
        {"next_cursor": str | None, "has_more": bool}}`.
        """
        cursor: str | None = None
        base_params = dict(params or {})
        while True:
            page_params = {**base_params, "limit": limit, "cursor": cursor}
            data = self.get(path, params=page_params, context=context)
            items = data.get(item_key, []) if data else []
            yield from items
            pagination = (data or {}).get("pagination") or {}
            if not pagination.get("has_more"):
                break
            cursor = pagination.get("next_cursor")
            if not cursor:
                break

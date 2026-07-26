from __future__ import annotations

import asyncio
from typing import Any

import httpx


class PokeAPIClient:
    """Read-only PokéAPI client with safe GET retries and a per-run memory cache."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        request_delay_seconds: float,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._delay = request_delay_seconds
        self._client: httpx.AsyncClient | None = None
        self._cache: dict[str, dict[str, Any]] = {}

    async def __aenter__(self) -> PokeAPIClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
            headers={"User-Agent": "PokemonDaily/1.0 (educational non-commercial bot)"},
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("PokeAPIClient must be used as an async context manager")
        return self._client

    async def get(self, url_or_path: str) -> dict[str, Any]:
        cache_key = url_or_path
        if cache_key in self._cache:
            return self._cache[cache_key]
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = await self.client.get(url_or_path)
                if response.status_code == 429 or 500 <= response.status_code:
                    response.raise_for_status()
                response.raise_for_status()
                payload = response.json()
                self._cache[cache_key] = payload
                if self._delay:
                    await asyncio.sleep(self._delay)
                return payload
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                if attempt < 3:
                    await asyncio.sleep(0.5 * 2 ** (attempt - 1))
        raise RuntimeError(f"PokéAPI request failed: {url_or_path}") from last_error

    async def evolution_chain_refs(self) -> list[dict[str, str]]:
        payload = await self.get("evolution-chain?limit=100000&offset=0")
        return list(payload["results"])

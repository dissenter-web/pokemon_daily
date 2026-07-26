from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

from app.domain.errors import (
    AmbiguousMaxError,
    PermanentMaxError,
    SafeRetryableMaxError,
)

logger = logging.getLogger(__name__)


class MaxAPIClient:
    def __init__(
        self,
        *,
        token: str,
        base_url: str,
        ca_bundle: Path,
        timeout_seconds: float = 12.0,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._ca_bundle = ca_bundle
        self._timeout = httpx.Timeout(
            connect=5.0,
            read=timeout_seconds,
            write=timeout_seconds,
            pool=5.0,
        )
        self._client: httpx.AsyncClient | None = None
        self._rate_lock = asyncio.Lock()
        self._last_request_started = 0.0
        self._minimum_request_interval = 0.1

    async def __aenter__(self) -> MaxAPIClient:
        if not self._token:
            logger.warning("max_api_token_not_configured")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": self._token},
            timeout=self._timeout,
            verify=str(self._ca_bundle),
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("MaxAPIClient must be used as an async context manager")
        if not self._token:
            raise PermanentMaxError("MAX_BOT_TOKEN is not configured")
        return self._client

    @staticmethod
    def _retry_after(response: httpx.Response) -> int | None:
        raw = response.headers.get("Retry-After")
        if raw and raw.isdigit():
            return min(int(raw), 3600)
        return None

    async def _post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with self._rate_lock:
            delay = (
                self._minimum_request_interval
                - (time.monotonic() - self._last_request_started)
            )
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request_started = time.monotonic()
        try:
            response = await self.client.post(path, params=params, json=json)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as error:
            raise SafeRetryableMaxError(type(error).__name__) from error
        except (
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.RemoteProtocolError,
        ) as error:
            raise AmbiguousMaxError(type(error).__name__) from error

        if response.is_success:
            if not response.content:
                return {}
            try:
                return response.json()
            except ValueError as error:
                raise AmbiguousMaxError(
                    "MAX returned a successful status with invalid JSON"
                ) from error

        detail = response.text[:300]
        if response.status_code in {429, 503}:
            raise SafeRetryableMaxError(
                f"MAX returned HTTP {response.status_code}: {detail}",
                retry_after_seconds=self._retry_after(response),
            )
        if 500 <= response.status_code:
            raise AmbiguousMaxError(
                f"MAX returned HTTP {response.status_code}: {detail}"
            )
        raise PermanentMaxError(
            f"MAX returned HTTP {response.status_code}: {detail}",
            status_code=response.status_code,
        )

    @staticmethod
    def keyboard(buttons: Sequence[Sequence[dict[str, str]]]) -> dict[str, Any]:
        return {
            "type": "inline_keyboard",
            "payload": {"buttons": [list(row) for row in buttons]},
        }

    async def send_message(
        self,
        *,
        max_user_id: int,
        text: str,
        buttons: Sequence[Sequence[dict[str, str]]] = (),
        image_url: str | None = None,
    ) -> str | None:
        attachments: list[dict[str, Any]] = []
        if image_url:
            attachments.append({"type": "image", "payload": {"url": image_url}})
        if buttons:
            attachments.append(self.keyboard(buttons))
        body: dict[str, Any] = {
            "text": text[:4000],
            "format": "html",
            "attachments": attachments,
        }
        try:
            payload = await self._post(
                "/messages",
                params={"user_id": max_user_id},
                json=body,
            )
        except PermanentMaxError as error:
            if not image_url or error.status_code != 400:
                raise
            logger.warning(
                "max_image_rejected_using_text_fallback",
                extra={"max_user_id": max_user_id},
            )
            body["attachments"] = [
                attachment
                for attachment in attachments
                if attachment.get("type") != "image"
            ]
            payload = await self._post(
                "/messages",
                params={"user_id": max_user_id},
                json=body,
            )
        message = payload.get("message") or {}
        body_payload = message.get("body") or {}
        value = body_payload.get("mid") or message.get("mid")
        return str(value) if value is not None else None

    async def register_webhook(
        self, *, url: str, secret: str, update_types: Sequence[str]
    ) -> dict[str, Any]:
        return await self._post(
            "/subscriptions",
            json={
                "url": url,
                "update_types": list(update_types),
                "secret": secret,
            },
        )

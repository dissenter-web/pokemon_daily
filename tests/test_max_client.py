from pathlib import Path

import httpx
import pytest

from app.clients.max_api import MaxAPIClient
from app.domain.errors import AmbiguousMaxError, SafeRetryableMaxError


def client_with_transport(transport: httpx.AsyncBaseTransport) -> MaxAPIClient:
    client = MaxAPIClient(
        token="test-token",
        base_url="https://platform-api2.max.ru",
        ca_bundle=Path("/unused-in-mock"),
    )
    client._client = httpx.AsyncClient(  # noqa: SLF001 - isolated boundary test
        base_url="https://platform-api2.max.ru",
        transport=transport,
    )
    return client


@pytest.mark.asyncio
async def test_503_is_safe_to_retry() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(503, request=request, text="unavailable")
    )
    client = client_with_transport(transport)
    try:
        with pytest.raises(SafeRetryableMaxError):
            await client.send_message(max_user_id=1, text="test")
    finally:
        await client._client.aclose()  # noqa: SLF001


@pytest.mark.asyncio
async def test_read_timeout_is_ambiguous_and_not_auto_retried() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    client = client_with_transport(httpx.MockTransport(timeout))
    try:
        with pytest.raises(AmbiguousMaxError):
            await client.send_message(max_user_id=1, text="test")
    finally:
        await client._client.aclose()  # noqa: SLF001


@pytest.mark.asyncio
async def test_definite_image_rejection_falls_back_to_text() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(400, request=request, text="bad image")
        return httpx.Response(
            200,
            request=request,
            json={"message": {"body": {"mid": "message-1"}}},
        )

    client = client_with_transport(httpx.MockTransport(handler))
    try:
        message_id = await client.send_message(
            max_user_id=1,
            text="test",
            image_url="https://example.com/image.png",
        )
    finally:
        await client._client.aclose()  # noqa: SLF001
    assert message_id == "message-1"
    assert requests[0]["attachments"][0]["type"] == "image"
    assert all(item["type"] != "image" for item in requests[1]["attachments"])


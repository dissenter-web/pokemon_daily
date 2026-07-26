from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.schemas.max_api import MaxUpdate
from app.services.webhook import WebhookService


@pytest.mark.asyncio
async def test_duplicate_webhook_does_not_dispatch_action() -> None:
    session = AsyncMock()
    service = WebhookService(
        session,
        SimpleNamespace(),
        Settings(environment="test"),
    )
    service.webhooks = SimpleNamespace(claim=AsyncMock(return_value=False))
    service._dispatch = AsyncMock()
    update = MaxUpdate.model_validate(
        {
            "update_type": "message_callback",
            "timestamp": 1,
            "callback": {
                "callback_id": "same-id",
                "payload": "stats",
                "user": {"user_id": 777},
            },
        }
    )

    assert not await service.process(update)
    service._dispatch.assert_not_awaited()


from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.domain.enums import DeliveryStatus
from app.services.delivery import DeliveryService, ManualDeliveryResult


@pytest.mark.asyncio
async def test_repeated_manual_request_does_not_select_a_new_pokemon() -> None:
    session = AsyncMock()
    max_client = SimpleNamespace(send_message=AsyncMock())
    settings = Settings(environment="test")
    service = DeliveryService(session, max_client, settings)
    existing = SimpleNamespace(status=DeliveryStatus.SENT)
    service.users = SimpleNamespace(lock=AsyncMock())
    service.deliveries = SimpleNamespace(
        get_for_day=AsyncMock(return_value=existing),
        get_unresolved=AsyncMock(),
    )
    service.catalog = SimpleNamespace(next_for_user=AsyncMock())
    user = SimpleNamespace(id=1, max_user_id=777)

    result = await service.deliver_manually(user)

    assert result == ManualDeliveryResult.ALREADY_SENT
    service.catalog.next_for_user.assert_not_awaited()
    max_client.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_unresolved_old_delivery_blocks_a_new_reservation() -> None:
    session = AsyncMock()
    max_client = SimpleNamespace(send_message=AsyncMock())
    service = DeliveryService(session, max_client, Settings(environment="test"))
    unresolved = SimpleNamespace(status=DeliveryStatus.RETRYABLE)
    service.users = SimpleNamespace(lock=AsyncMock())
    service.deliveries = SimpleNamespace(
        get_for_day=AsyncMock(return_value=None),
        get_unresolved=AsyncMock(return_value=unresolved),
    )
    service.catalog = SimpleNamespace(next_for_user=AsyncMock())
    user = SimpleNamespace(id=1, max_user_id=777)

    reservation = await service.reserve_for_user(user)

    assert reservation is unresolved
    service.catalog.next_for_user.assert_not_awaited()


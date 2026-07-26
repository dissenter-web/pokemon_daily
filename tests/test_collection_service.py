from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.collection import CollectionService


@pytest.mark.asyncio
async def test_add_favorite_is_idempotent_repository_operation() -> None:
    session = AsyncMock()
    service = CollectionService(session, page_size=5)
    service.collection = SimpleNamespace(
        contains=AsyncMock(return_value=True),
        add_favorite=AsyncMock(),
        remove_favorite=AsyncMock(),
    )

    assert await service.set_favorite(1, 10, favorite=True)
    service.collection.add_favorite.assert_awaited_once_with(1, 10)
    service.collection.remove_favorite.assert_not_awaited()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_favorite_and_reject_unopened_pokemon() -> None:
    session = AsyncMock()
    service = CollectionService(session, page_size=5)
    service.collection = SimpleNamespace(
        contains=AsyncMock(side_effect=[True, False]),
        add_favorite=AsyncMock(),
        remove_favorite=AsyncMock(),
    )

    assert await service.set_favorite(1, 10, favorite=False)
    assert not await service.set_favorite(1, 11, favorite=True)
    service.collection.remove_favorite.assert_awaited_once_with(1, 10)
    service.collection.add_favorite.assert_not_awaited()


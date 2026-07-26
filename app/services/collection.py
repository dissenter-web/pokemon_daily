from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.domain.entities import CollectionPage, PokemonCard, UserStatistics
from app.repositories.catalog import CatalogRepository
from app.repositories.collections import CollectionRepository


class CollectionService:
    def __init__(self, session: AsyncSession, page_size: int) -> None:
        self.session = session
        self.page_size = page_size
        self.collection = CollectionRepository(session)
        self.catalog = CatalogRepository(session)

    async def page(
        self, user_id: int, page: int, *, favorites_only: bool = False
    ) -> CollectionPage:
        return await self.collection.page(
            user_id=user_id,
            page=page,
            page_size=self.page_size,
            favorites_only=favorites_only,
        )

    async def set_favorite(
        self, user_id: int, pokemon_id: int, *, favorite: bool
    ) -> bool:
        if not await self.collection.contains(user_id, pokemon_id):
            return False
        if favorite:
            await self.collection.add_favorite(user_id, pokemon_id)
        else:
            await self.collection.remove_favorite(user_id, pokemon_id)
        await self.session.commit()
        return True

    async def card(self, user_id: int, pokemon_id: int) -> tuple[PokemonCard, bool]:
        card = await self.catalog.card(pokemon_id)
        is_favorite = await self.collection.is_favorite(user_id, pokemon_id)
        return card, is_favorite

    async def statistics(self, user: User) -> UserStatistics:
        available = await self.catalog.available_count()
        return await self.collection.statistics(user, available)

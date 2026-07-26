from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    DailyDelivery,
    EvolutionChain,
    EvolutionStage,
    Favorite,
    Pokemon,
    PokemonSpecies,
    User,
    UserCollection,
)
from app.domain.entities import (
    CollectionItem,
    CollectionPage,
    UserStatistics,
)
from app.domain.enums import DeliveryStatus


class CollectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def contains(self, user_id: int, pokemon_id: int) -> bool:
        result = await self.session.execute(
            select(UserCollection.id).where(
                UserCollection.user_id == user_id,
                UserCollection.pokemon_id == pokemon_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def is_favorite(self, user_id: int, pokemon_id: int) -> bool:
        result = await self.session.execute(
            select(Favorite.id).where(
                Favorite.user_id == user_id,
                Favorite.pokemon_id == pokemon_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def add_favorite(self, user_id: int, pokemon_id: int) -> None:
        await self.session.execute(
            insert(Favorite)
            .values(user_id=user_id, pokemon_id=pokemon_id)
            .on_conflict_do_nothing(
                index_elements=[Favorite.user_id, Favorite.pokemon_id]
            )
        )

    async def remove_favorite(self, user_id: int, pokemon_id: int) -> None:
        favorite = await self.session.execute(
            select(Favorite).where(
                Favorite.user_id == user_id,
                Favorite.pokemon_id == pokemon_id,
            )
        )
        entity = favorite.scalar_one_or_none()
        if entity is not None:
            await self.session.delete(entity)

    async def page(
        self, user_id: int, page: int, page_size: int, favorites_only: bool = False
    ) -> CollectionPage:
        count_statement = select(func.count(UserCollection.id)).where(
            UserCollection.user_id == user_id
        )
        statement = (
            select(
                Pokemon.id,
                PokemonSpecies.pokedex_number,
                PokemonSpecies.name_ru,
                PokemonSpecies.name_en,
                UserCollection.obtained_at,
            )
            .join(Pokemon, Pokemon.id == UserCollection.pokemon_id)
            .join(PokemonSpecies, PokemonSpecies.id == Pokemon.species_id)
            .where(UserCollection.user_id == user_id)
        )
        if favorites_only:
            statement = statement.join(
                Favorite,
                (Favorite.pokemon_id == Pokemon.id)
                & (Favorite.user_id == user_id),
            )
            count_statement = (
                select(func.count(Favorite.id))
                .join(
                    UserCollection,
                    (UserCollection.pokemon_id == Favorite.pokemon_id)
                    & (UserCollection.user_id == Favorite.user_id),
                )
                .where(Favorite.user_id == user_id)
            )
        total = int((await self.session.execute(count_statement)).scalar_one())
        max_page = max(0, (total - 1) // page_size)
        normalized_page = min(max(page, 0), max_page)
        rows = await self.session.execute(
            statement.order_by(UserCollection.obtained_at, UserCollection.id)
            .offset(normalized_page * page_size)
            .limit(page_size)
        )
        items = tuple(
            CollectionItem(
                pokemon_id=row.id,
                pokedex_number=row.pokedex_number,
                name_ru=row.name_ru or row.name_en,
                name_en=row.name_en,
                obtained_at=row.obtained_at,
            )
            for row in rows
        )
        return CollectionPage(
            items=items,
            page=normalized_page,
            total_items=total,
            page_size=page_size,
        )

    async def statistics(self, user: User, available: int) -> UserStatistics:
        opened = int(
            (
                await self.session.execute(
                    select(func.count(UserCollection.id)).where(
                        UserCollection.user_id == user.id
                    )
                )
            ).scalar_one()
        )
        favorites = int(
            (
                await self.session.execute(
                    select(func.count(Favorite.id)).where(Favorite.user_id == user.id)
                )
            ).scalar_one()
        )
        delivery_row = (
            await self.session.execute(
                select(
                    func.count(DailyDelivery.id).label("successful"),
                    func.max(DailyDelivery.sent_at).label("last_received"),
                ).where(
                    DailyDelivery.user_id == user.id,
                    DailyDelivery.status == DeliveryStatus.SENT,
                )
            )
        ).one()
        current = (
            await self.session.execute(
                select(EvolutionChain.sequence_order, EvolutionStage.stage_order)
                .join(EvolutionStage, EvolutionStage.chain_id == EvolutionChain.id)
                .join(PokemonSpecies, PokemonSpecies.id == EvolutionStage.species_id)
                .join(Pokemon, Pokemon.species_id == PokemonSpecies.id)
                .join(DailyDelivery, DailyDelivery.pokemon_id == Pokemon.id)
                .where(
                    DailyDelivery.user_id == user.id,
                    DailyDelivery.status == DeliveryStatus.SENT,
                )
                .order_by(DailyDelivery.sent_at.desc())
                .limit(1)
            )
        ).one_or_none()
        return UserStatistics(
            opened=opened,
            available=available,
            favorites=favorites,
            started_at=user.started_at,
            last_received_at=delivery_row.last_received,
            successful_deliveries=int(delivery_row.successful),
            current_chain=current.sequence_order if current else None,
            current_stage=current.stage_order if current else None,
        )


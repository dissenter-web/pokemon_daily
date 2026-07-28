from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Ability,
    EvolutionChain,
    EvolutionStage,
    Pokemon,
    PokemonAbilityLink,
    PokemonSpecies,
    PokemonType,
    PokemonTypeLink,
    UserCollection,
)
from app.domain.entities import PokemonCard


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _ordered_catalog(self) -> Select[tuple[Pokemon]]:
        return (
            select(Pokemon)
            .join(PokemonSpecies, Pokemon.species_id == PokemonSpecies.id)
            .join(EvolutionStage, EvolutionStage.species_id == PokemonSpecies.id)
            .join(EvolutionChain, EvolutionChain.id == EvolutionStage.chain_id)
            .where(
                Pokemon.is_default.is_(True),
                PokemonSpecies.content_ready.is_(True),
            )
            .order_by(
                EvolutionChain.sequence_order,
                EvolutionStage.stage_order,
                EvolutionStage.branch_order,
                Pokemon.pokeapi_id,
            )
        )

    async def first_available(self) -> Pokemon | None:
        result = await self.session.execute(
            self._ordered_catalog().limit(1)
        )
        return result.scalar_one_or_none()

    async def first_available_many(self, limit: int) -> list[Pokemon]:
        result = await self.session.execute(
            self._ordered_catalog().limit(limit)
        )
        return list(result.scalars().all())

    async def next_for_user(self, user_id: int) -> Pokemon | None:
        statement = (
            self._ordered_catalog()
            .outerjoin(
                UserCollection,
                (UserCollection.pokemon_id == Pokemon.id)
                & (UserCollection.user_id == user_id),
            )
            .where(UserCollection.id.is_(None))
            .limit(1)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def available_count(self) -> int:
        result = await self.session.execute(
            select(func.count(Pokemon.id))
            .join(PokemonSpecies, Pokemon.species_id == PokemonSpecies.id)
            .where(
                Pokemon.is_default.is_(True),
                PokemonSpecies.content_ready.is_(True),
            )
        )
        return int(result.scalar_one())

    async def card(self, pokemon_id: int) -> PokemonCard:
        result = await self.session.execute(
            select(Pokemon, PokemonSpecies, EvolutionStage)
            .join(PokemonSpecies, Pokemon.species_id == PokemonSpecies.id)
            .join(EvolutionStage, EvolutionStage.species_id == PokemonSpecies.id)
            .where(Pokemon.id == pokemon_id)
        )
        pokemon, species, current_stage = result.one()

        type_result = await self.session.execute(
            select(PokemonType)
            .join(PokemonTypeLink, PokemonTypeLink.type_id == PokemonType.id)
            .where(PokemonTypeLink.pokemon_id == pokemon_id)
            .order_by(PokemonTypeLink.slot)
        )
        ability_result = await self.session.execute(
            select(Ability)
            .join(PokemonAbilityLink, PokemonAbilityLink.ability_id == Ability.id)
            .where(PokemonAbilityLink.pokemon_id == pokemon_id)
            .order_by(PokemonAbilityLink.slot)
        )
        chain_result = await self.session.execute(
            select(PokemonSpecies, EvolutionStage)
            .join(EvolutionStage, EvolutionStage.species_id == PokemonSpecies.id)
            .where(EvolutionStage.chain_id == current_stage.chain_id)
            .order_by(EvolutionStage.stage_order, EvolutionStage.branch_order)
        )
        chain_rows = list(chain_result.all())
        evolution_names = tuple(
            chain_species.name_ru or chain_species.name_en
            for chain_species, _ in chain_rows
        )
        evolution_index = next(
            index
            for index, (chain_species, _) in enumerate(chain_rows)
            if chain_species.id == species.id
        )
        types = tuple(item.name_ru or item.name_en for item in type_result.scalars())
        abilities = tuple(
            item.name_ru or item.name_en for item in ability_result.scalars()
        )
        return PokemonCard(
            pokemon_id=pokemon.id,
            pokedex_number=species.pokedex_number,
            name_ru=species.name_ru or species.name_en,
            name_en=species.name_en,
            description_ru=species.description_ru or "Описание готовится.",
            fact_ru=species.fact_ru or "Факт готовится.",
            image_url=pokemon.image_url,
            types=types,
            abilities=abilities,
            evolution_names=evolution_names,
            evolution_index=evolution_index,
        )


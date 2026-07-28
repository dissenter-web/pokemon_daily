import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.pokeapi import PokeAPIClient
from app.db.models import (
    Ability,
    EvolutionChain,
    EvolutionStage,
    Pokemon,
    PokemonAbilityLink,
    PokemonSpecies,
    PokemonType,
    PokemonTypeLink,
    SyncRun,
)
from app.domain.enums import SyncStatus

logger = logging.getLogger(__name__)

TYPE_NAMES_RU = {
    "normal": "Обычный",
    "fire": "Огонь",
    "water": "Вода",
    "electric": "Электричество",
    "grass": "Трава",
    "ice": "Лёд",
    "fighting": "Боевой",
    "poison": "Яд",
    "ground": "Земля",
    "flying": "Полёт",
    "psychic": "Психический",
    "bug": "Насекомое",
    "rock": "Камень",
    "ghost": "Призрак",
    "dragon": "Дракон",
    "dark": "Тьма",
    "steel": "Сталь",
    "fairy": "Фея",
}

ABILITY_NAMES_RU = {
    "overgrow": "Зарастание",
    "chlorophyll": "Хлорофилл",
    "blaze": "Пламя",
    "solar-power": "Солнечная сила",
    "torrent": "Поток",
    "rain-dish": "Чаша дождя",
}


@dataclass(frozen=True, slots=True)
class FlattenedSpecies:
    name: str
    url: str
    depth: int
    branch_order: int


def resource_id(url: str) -> int:
    return int(url.rstrip("/").rsplit("/", 1)[-1])


def flatten_chain(root: dict[str, Any]) -> list[FlattenedSpecies]:
    flattened: list[FlattenedSpecies] = []
    branch_order = 0

    def visit(node: dict[str, Any], depth: int) -> None:
        nonlocal branch_order
        species = node["species"]
        flattened.append(
            FlattenedSpecies(
                name=species["name"],
                url=species["url"],
                depth=depth,
                branch_order=branch_order,
            )
        )
        branch_order += 1
        children = sorted(
            node.get("evolves_to") or [],
            key=lambda item: resource_id(item["species"]["url"]),
        )
        for child in children:
            visit(child, depth + 1)

    visit(root, 0)
    return sorted(flattened, key=lambda item: (item.depth, item.branch_order))


class CatalogSyncService:
    def __init__(
        self,
        session: AsyncSession,
        client: PokeAPIClient,
        editorial_content_path: Path,
    ) -> None:
        self.session = session
        self.client = client
        self.editorial = self._load_editorial(editorial_content_path)

    @staticmethod
    def _load_editorial(path: Path) -> dict[str, dict[str, str]]:
        if not path.exists():
            raise FileNotFoundError(f"Editorial directory not found: {path}")

        if not path.is_dir():
            raise ValueError(f"Expected directory, got file: {path}")

        entries: dict[str, dict[str, str]] = {}

        for json_file in sorted(path.glob("*.json")):
            payload = json.loads(json_file.read_text(encoding="utf-8"))

            file_entries = payload.get("entries")
            if not isinstance(file_entries, dict):
                raise ValueError(
                    f"{json_file.name} must contain an 'entries' object"
                )

            for slug, content in file_entries.items():
                if slug in entries:
                    raise ValueError(
                        f"Duplicate editorial entry '{slug}' "
                  	      f"found in {json_file.name}"
                    )

                entries[slug] = content

        return entries

    async def run(self, max_chains: int = 0) -> tuple[int, int]:
        sync_run = SyncRun(status=SyncStatus.RUNNING)
        self.session.add(sync_run)
        await self.session.commit()
        await self.session.refresh(sync_run)

        chains_processed = 0
        pokemon_processed = 0
        try:
            refs = await self.client.evolution_chain_refs()
            refs.sort(key=lambda item: resource_id(item["url"]))
            if max_chains > 0:
                refs = refs[:max_chains]
            for chain_ref in refs:
                sequence_order = resource_id(chain_ref["url"])
                count = await self._sync_chain(chain_ref["url"], sequence_order)
                chains_processed += 1
                pokemon_processed += count
                await self.session.execute(
                    update(SyncRun)
                    .where(SyncRun.id == sync_run.id)
                    .values(
                        chains_processed=chains_processed,
                        pokemon_processed=pokemon_processed,
                    )
                )
                await self.session.commit()
                logger.info(
                    "catalog_chain_synchronized",
                    extra={
                        "chain": chains_processed,
                        "pokemon_total": pokemon_processed,
                    },
                )
        except Exception as error:
            await self.session.rollback()
            await self.session.execute(
                update(SyncRun)
                .where(SyncRun.id == sync_run.id)
                .values(
                    status=SyncStatus.FAILED,
                    finished_at=datetime.now(UTC),
                    error_detail=str(error)[:500],
                    chains_processed=chains_processed,
                    pokemon_processed=pokemon_processed,
                )
            )
            await self.session.commit()
            logger.exception("catalog_sync_failed")
            raise

        await self.session.execute(
            update(SyncRun)
            .where(SyncRun.id == sync_run.id)
            .values(
                status=SyncStatus.SUCCEEDED,
                finished_at=datetime.now(UTC),
                chains_processed=chains_processed,
                pokemon_processed=pokemon_processed,
            )
        )
        await self.session.commit()
        logger.info(
            "catalog_sync_succeeded",
            extra={
                "chains_processed": chains_processed,
                "pokemon_processed": pokemon_processed,
            },
        )
        return chains_processed, pokemon_processed

    async def _sync_chain(self, url: str, sequence_order: int) -> int:
        payload = await self.client.get(url)
        chain_id = int(payload["id"])
        chain_db_id = await self._upsert_chain(chain_id, sequence_order)
        flattened = flatten_chain(payload["chain"])
        for item in flattened:
            species_payload = await self.client.get(item.url)
            species_db_id = await self._upsert_species(
                species_payload, chain_db_id
            )
            pokemon_payload = await self._default_pokemon(species_payload)
            pokemon_db_id = await self._upsert_pokemon(
                pokemon_payload, species_db_id
            )
            await self._replace_types(pokemon_db_id, pokemon_payload)
            await self._replace_abilities(pokemon_db_id, pokemon_payload)
            await self._upsert_stage(
                chain_db_id,
                species_db_id,
                item.depth,
                item.branch_order,
            )
        return len(flattened)

    async def _upsert_chain(self, pokeapi_id: int, sequence_order: int) -> int:
        await self.session.execute(
            insert(EvolutionChain)
            .values(pokeapi_id=pokeapi_id, sequence_order=sequence_order)
            .on_conflict_do_update(
                index_elements=[EvolutionChain.pokeapi_id],
                set_={"sequence_order": sequence_order},
            )
        )
        result = await self.session.execute(
            select(EvolutionChain.id).where(
                EvolutionChain.pokeapi_id == pokeapi_id
            )
        )
        return result.scalar_one()

    async def _upsert_species(
        self, payload: dict[str, Any], chain_db_id: int
    ) -> int:
        slug = payload["name"]
        editorial = self.editorial.get(slug, {})
        name_ru = editorial.get("name_ru")
        description = editorial.get("description_ru")
        fact = editorial.get("fact_ru")
        content_ready = bool(name_ru and description and fact)
        values = {
            "pokeapi_id": int(payload["id"]),
            "slug": slug,
            "name_en": slug.replace("-", " ").title(),
            "name_ru": name_ru,
            "pokedex_number": int(payload["id"]),
            "description_ru": description,
            "fact_ru": fact,
            "content_source_url": editorial.get("source_url"),
            "content_ready": content_ready,
            "evolution_chain_id": chain_db_id,
        }
        statement = insert(PokemonSpecies).values(**values)
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[PokemonSpecies.pokeapi_id],
                set_={
                    key: getattr(statement.excluded, key)
                    for key in values
                    if key != "pokeapi_id"
                },
            )
        )
        result = await self.session.execute(
            select(PokemonSpecies.id).where(
                PokemonSpecies.pokeapi_id == int(payload["id"])
            )
        )
        return result.scalar_one()

    async def _default_pokemon(self, species: dict[str, Any]) -> dict[str, Any]:
        varieties = species.get("varieties") or []
        default = next(
            (item["pokemon"] for item in varieties if item.get("is_default")),
            varieties[0]["pokemon"] if varieties else None,
        )
        if default is None:
            raise ValueError(f"species {species['name']} has no Pokemon variety")
        return await self.client.get(default["url"])

    async def _upsert_pokemon(
        self, payload: dict[str, Any], species_db_id: int
    ) -> int:
        artwork = (
            ((payload.get("sprites") or {}).get("other") or {})
            .get("official-artwork", {})
            .get("front_default")
        )
        fallback = (payload.get("sprites") or {}).get("front_default")
        values = {
            "pokeapi_id": int(payload["id"]),
            "species_id": species_db_id,
            "slug": payload["name"],
            "is_default": bool(payload.get("is_default", True)),
            "image_url": artwork or fallback,
        }
        statement = insert(Pokemon).values(**values)
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[Pokemon.pokeapi_id],
                set_={
                    key: getattr(statement.excluded, key)
                    for key in values
                    if key != "pokeapi_id"
                },
            )
        )
        result = await self.session.execute(
            select(Pokemon.id).where(Pokemon.pokeapi_id == int(payload["id"]))
        )
        return result.scalar_one()

    async def _replace_types(
        self, pokemon_db_id: int, payload: dict[str, Any]
    ) -> None:
        await self.session.execute(
            delete(PokemonTypeLink).where(
                PokemonTypeLink.pokemon_id == pokemon_db_id
            )
        )
        for item in sorted(payload.get("types") or [], key=lambda value: value["slot"]):
            resource = item["type"]
            pokeapi_id = resource_id(resource["url"])
            slug = resource["name"]
            statement = insert(PokemonType).values(
                pokeapi_id=pokeapi_id,
                slug=slug,
                name_en=slug.replace("-", " ").title(),
                name_ru=TYPE_NAMES_RU.get(slug),
            )
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[PokemonType.pokeapi_id],
                    set_={
                        "slug": statement.excluded.slug,
                        "name_en": statement.excluded.name_en,
                        "name_ru": statement.excluded.name_ru,
                    },
                )
            )
            type_id = (
                await self.session.execute(
                    select(PokemonType.id).where(
                        PokemonType.pokeapi_id == pokeapi_id
                    )
                )
            ).scalar_one()
            self.session.add(
                PokemonTypeLink(
                    pokemon_id=pokemon_db_id,
                    type_id=type_id,
                    slot=int(item["slot"]),
                )
            )

    async def _replace_abilities(
        self, pokemon_db_id: int, payload: dict[str, Any]
    ) -> None:
        await self.session.execute(
            delete(PokemonAbilityLink).where(
                PokemonAbilityLink.pokemon_id == pokemon_db_id
            )
        )
        for item in sorted(
            payload.get("abilities") or [], key=lambda value: value["slot"]
        ):
            resource = item.get("ability")
            if not resource:
                continue
            pokeapi_id = resource_id(resource["url"])
            slug = resource["name"]
            statement = insert(Ability).values(
                pokeapi_id=pokeapi_id,
                slug=slug,
                name_en=slug.replace("-", " ").title(),
                name_ru=ABILITY_NAMES_RU.get(slug),
            )
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[Ability.pokeapi_id],
                    set_={
                        "slug": statement.excluded.slug,
                        "name_en": statement.excluded.name_en,
                        "name_ru": statement.excluded.name_ru,
                    },
                )
            )
            ability_id = (
                await self.session.execute(
                    select(Ability.id).where(Ability.pokeapi_id == pokeapi_id)
                )
            ).scalar_one()
            self.session.add(
                PokemonAbilityLink(
                    pokemon_id=pokemon_db_id,
                    ability_id=ability_id,
                    slot=int(item["slot"]),
                    is_hidden=bool(item.get("is_hidden")),
                )
            )

    async def _upsert_stage(
        self,
        chain_db_id: int,
        species_db_id: int,
        stage_order: int,
        branch_order: int,
    ) -> None:
        statement = insert(EvolutionStage).values(
            chain_id=chain_db_id,
            species_id=species_db_id,
            stage_order=stage_order,
            branch_order=branch_order,
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[EvolutionStage.species_id],
                set_={
                    "chain_id": statement.excluded.chain_id,
                    "stage_order": statement.excluded.stage_order,
                    "branch_order": statement.excluded.branch_order,
                },
            )
        )

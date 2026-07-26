from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PokemonCard:
    pokemon_id: int
    pokedex_number: int
    name_ru: str
    name_en: str
    description_ru: str
    fact_ru: str
    image_url: str | None
    types: tuple[str, ...]
    abilities: tuple[str, ...]
    evolution_names: tuple[str, ...]
    evolution_index: int


@dataclass(frozen=True, slots=True)
class CollectionItem:
    pokemon_id: int
    pokedex_number: int
    name_ru: str
    name_en: str
    obtained_at: datetime


@dataclass(frozen=True, slots=True)
class CollectionPage:
    items: tuple[CollectionItem, ...]
    page: int
    total_items: int
    page_size: int

    @property
    def total_pages(self) -> int:
        if self.total_items == 0:
            return 1
        return (self.total_items + self.page_size - 1) // self.page_size


@dataclass(frozen=True, slots=True)
class UserStatistics:
    opened: int
    available: int
    favorites: int
    started_at: datetime
    last_received_at: datetime | None
    successful_deliveries: int
    current_chain: int | None
    current_stage: int | None

    @property
    def completion_percent(self) -> float:
        if not self.available:
            return 0.0
        return round(self.opened * 100 / self.available, 1)


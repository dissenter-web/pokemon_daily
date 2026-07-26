from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.enums import DeliveryStatus, SyncStatus, WebhookStatus


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    max_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    max_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EvolutionChain(Base):
    __tablename__ = "evolution_chains"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pokeapi_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)


class PokemonSpecies(Base):
    __tablename__ = "pokemon_species"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pokeapi_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    name_en: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ru: Mapped[str | None] = mapped_column(String(120))
    pokedex_number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    description_ru: Mapped[str | None] = mapped_column(Text)
    fact_ru: Mapped[str | None] = mapped_column(Text)
    content_source_url: Mapped[str | None] = mapped_column(String(500))
    content_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evolution_chain_id: Mapped[int] = mapped_column(
        ForeignKey("evolution_chains.id", ondelete="CASCADE"), nullable=False
    )

    evolution_chain: Mapped[EvolutionChain] = relationship()
    pokemon: Mapped[list[Pokemon]] = relationship(back_populates="species")
    evolution_stage: Mapped[EvolutionStage] = relationship(
        back_populates="species", uselist=False
    )


class PokemonType(Base):
    __tablename__ = "types"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pokeapi_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name_en: Mapped[str] = mapped_column(String(80), nullable=False)
    name_ru: Mapped[str | None] = mapped_column(String(80))


class Ability(Base):
    __tablename__ = "abilities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pokeapi_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    name_en: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ru: Mapped[str | None] = mapped_column(String(120))


class Pokemon(Base):
    __tablename__ = "pokemon"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pokeapi_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    image_url: Mapped[str | None] = mapped_column(String(500))

    species: Mapped[PokemonSpecies] = relationship(back_populates="pokemon")
    types: Mapped[list[PokemonType]] = relationship(secondary="pokemon_types")
    abilities: Mapped[list[Ability]] = relationship(secondary="pokemon_abilities")


class PokemonTypeLink(Base):
    __tablename__ = "pokemon_types"

    pokemon_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon.id", ondelete="CASCADE"), primary_key=True
    )
    type_id: Mapped[int] = mapped_column(
        ForeignKey("types.id", ondelete="CASCADE"), primary_key=True
    )
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("pokemon_id", "slot"),)


class PokemonAbilityLink(Base):
    __tablename__ = "pokemon_abilities"

    pokemon_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon.id", ondelete="CASCADE"), primary_key=True
    )
    ability_id: Mapped[int] = mapped_column(
        ForeignKey("abilities.id", ondelete="CASCADE"), primary_key=True
    )
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint("pokemon_id", "slot"),)


class EvolutionStage(Base):
    __tablename__ = "evolution_stages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chain_id: Mapped[int] = mapped_column(
        ForeignKey("evolution_chains.id", ondelete="CASCADE"), nullable=False
    )
    species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False)
    branch_order: Mapped[int] = mapped_column(Integer, nullable=False)

    species: Mapped[PokemonSpecies] = relationship(back_populates="evolution_stage")
    __table_args__ = (
        UniqueConstraint("chain_id", "stage_order", "branch_order"),
        CheckConstraint("stage_order >= 0", name="stage_order_nonnegative"),
        CheckConstraint("branch_order >= 0", name="branch_order_nonnegative"),
    )


class DailyDelivery(Base):
    __tablename__ = "daily_deliveries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    pokemon_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon.id", ondelete="RESTRICT"), nullable=False
    )
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(
            DeliveryStatus,
            name="delivery_status",
            values_callable=lambda enum: [x.value for x in enum],
        ),
        nullable=False,
        default=DeliveryStatus.PENDING,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_message_id: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_detail: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "delivery_date"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        Index("ix_daily_deliveries_due", "status", "next_attempt_at"),
    )


class UserCollection(Base):
    __tablename__ = "user_collections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    pokemon_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon.id", ondelete="RESTRICT"), nullable=False
    )
    delivery_id: Mapped[int] = mapped_column(
        ForeignKey("daily_deliveries.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    obtained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "pokemon_id"),)


class Favorite(Base):
    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    pokemon_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("user_id", "pokemon_id"),)


class ProcessedWebhookUpdate(Base):
    __tablename__ = "processed_webhook_updates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    update_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    update_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[WebhookStatus] = mapped_column(
        Enum(
            WebhookStatus,
            name="webhook_status",
            values_callable=lambda enum: [x.value for x in enum],
        ),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_detail: Mapped[str | None] = mapped_column(String(500))


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, name="sync_status", values_callable=lambda enum: [x.value for x in enum]),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chains_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pokemon_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_detail: Mapped[str | None] = mapped_column(String(500))

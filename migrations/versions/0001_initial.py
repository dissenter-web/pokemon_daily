"""Initial normalized Pokemon Daily schema.

Revision ID: 0001
Revises:
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

delivery_status = postgresql.ENUM(
    "pending",
    "sending",
    "sent",
    "retryable",
    "permanently_failed",
    name="delivery_status",
    create_type=False,
)
webhook_status = postgresql.ENUM(
    "processing",
    "processed",
    "failed",
    name="webhook_status",
    create_type=False,
)
sync_status = postgresql.ENUM(
    "running",
    "succeeded",
    "failed",
    name="sync_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    delivery_status.create(bind, checkfirst=True)
    webhook_status.create(bind, checkfirst=True)
    sync_status.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("max_user_id", sa.BigInteger(), nullable=False),
        sa.Column("max_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_interaction_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("max_user_id", name="uq_users_max_user_id"),
    )
    op.create_table(
        "evolution_chains",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("pokeapi_id", sa.Integer(), nullable=False),
        sa.Column("sequence_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_evolution_chains"),
        sa.UniqueConstraint(
            "pokeapi_id", name="uq_evolution_chains_pokeapi_id"
        ),
        sa.UniqueConstraint(
            "sequence_order", name="uq_evolution_chains_sequence_order"
        ),
    )
    op.create_table(
        "types",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("pokeapi_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name_en", sa.String(length=80), nullable=False),
        sa.Column("name_ru", sa.String(length=80), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_types"),
        sa.UniqueConstraint("pokeapi_id", name="uq_types_pokeapi_id"),
        sa.UniqueConstraint("slug", name="uq_types_slug"),
    )
    op.create_table(
        "abilities",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("pokeapi_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name_en", sa.String(length=120), nullable=False),
        sa.Column("name_ru", sa.String(length=120), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_abilities"),
        sa.UniqueConstraint("pokeapi_id", name="uq_abilities_pokeapi_id"),
        sa.UniqueConstraint("slug", name="uq_abilities_slug"),
    )
    op.create_table(
        "pokemon_species",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("pokeapi_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name_en", sa.String(length=120), nullable=False),
        sa.Column("name_ru", sa.String(length=120), nullable=True),
        sa.Column("pokedex_number", sa.Integer(), nullable=False),
        sa.Column("description_ru", sa.Text(), nullable=True),
        sa.Column("fact_ru", sa.Text(), nullable=True),
        sa.Column("content_source_url", sa.String(length=500), nullable=True),
        sa.Column(
            "content_ready", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("evolution_chain_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evolution_chain_id"],
            ["evolution_chains.id"],
            name="fk_pokemon_species_evolution_chain_id_evolution_chains",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pokemon_species"),
        sa.UniqueConstraint(
            "pokeapi_id", name="uq_pokemon_species_pokeapi_id"
        ),
        sa.UniqueConstraint("slug", name="uq_pokemon_species_slug"),
        sa.UniqueConstraint(
            "pokedex_number", name="uq_pokemon_species_pokedex_number"
        ),
    )
    op.create_table(
        "pokemon",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("pokeapi_id", sa.Integer(), nullable=False),
        sa.Column("species_id", sa.BigInteger(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["species_id"],
            ["pokemon_species.id"],
            name="fk_pokemon_species_id_pokemon_species",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pokemon"),
        sa.UniqueConstraint("pokeapi_id", name="uq_pokemon_pokeapi_id"),
        sa.UniqueConstraint("slug", name="uq_pokemon_slug"),
    )
    op.create_table(
        "evolution_stages",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("chain_id", sa.BigInteger(), nullable=False),
        sa.Column("species_id", sa.BigInteger(), nullable=False),
        sa.Column("stage_order", sa.Integer(), nullable=False),
        sa.Column("branch_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "stage_order >= 0", name="ck_evolution_stages_stage_order_nonnegative"
        ),
        sa.CheckConstraint(
            "branch_order >= 0",
            name="ck_evolution_stages_branch_order_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["chain_id"],
            ["evolution_chains.id"],
            name="fk_evolution_stages_chain_id_evolution_chains",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["species_id"],
            ["pokemon_species.id"],
            name="fk_evolution_stages_species_id_pokemon_species",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evolution_stages"),
        sa.UniqueConstraint(
            "chain_id",
            "stage_order",
            "branch_order",
            name="uq_evolution_stages_chain_id",
        ),
        sa.UniqueConstraint(
            "species_id", name="uq_evolution_stages_species_id"
        ),
    )
    op.create_table(
        "pokemon_types",
        sa.Column("pokemon_id", sa.BigInteger(), nullable=False),
        sa.Column("type_id", sa.BigInteger(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["pokemon_id"],
            ["pokemon.id"],
            name="fk_pokemon_types_pokemon_id_pokemon",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["type_id"],
            ["types.id"],
            name="fk_pokemon_types_type_id_types",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("pokemon_id", "type_id", name="pk_pokemon_types"),
        sa.UniqueConstraint(
            "pokemon_id", "slot", name="uq_pokemon_types_pokemon_id"
        ),
    )
    op.create_table(
        "pokemon_abilities",
        sa.Column("pokemon_id", sa.BigInteger(), nullable=False),
        sa.Column("ability_id", sa.BigInteger(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["ability_id"],
            ["abilities.id"],
            name="fk_pokemon_abilities_ability_id_abilities",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pokemon_id"],
            ["pokemon.id"],
            name="fk_pokemon_abilities_pokemon_id_pokemon",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "pokemon_id", "ability_id", name="pk_pokemon_abilities"
        ),
        sa.UniqueConstraint(
            "pokemon_id", "slot", name="uq_pokemon_abilities_pokemon_id"
        ),
    )
    op.create_table(
        "daily_deliveries",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("pokemon_id", sa.BigInteger(), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("status", delivery_status, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_message_id", sa.String(length=200), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_detail", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_daily_deliveries_attempt_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["pokemon_id"],
            ["pokemon.id"],
            name="fk_daily_deliveries_pokemon_id_pokemon",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_daily_deliveries_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_daily_deliveries"),
        sa.UniqueConstraint(
            "user_id",
            "delivery_date",
            name="uq_daily_deliveries_user_id",
        ),
    )
    op.create_index(
        "ix_daily_deliveries_due",
        "daily_deliveries",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_table(
        "user_collections",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("pokemon_id", sa.BigInteger(), nullable=False),
        sa.Column("delivery_id", sa.BigInteger(), nullable=False),
        sa.Column("obtained_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["daily_deliveries.id"],
            name="fk_user_collections_delivery_id_daily_deliveries",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pokemon_id"],
            ["pokemon.id"],
            name="fk_user_collections_pokemon_id_pokemon",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_collections_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_collections"),
        sa.UniqueConstraint(
            "delivery_id", name="uq_user_collections_delivery_id"
        ),
        sa.UniqueConstraint(
            "user_id", "pokemon_id", name="uq_user_collections_user_id"
        ),
    )
    op.create_table(
        "favorites",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("pokemon_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["pokemon_id"],
            ["pokemon.id"],
            name="fk_favorites_pokemon_id_pokemon",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_favorites_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_favorites"),
        sa.UniqueConstraint(
            "user_id", "pokemon_id", name="uq_favorites_user_id"
        ),
    )
    op.create_table(
        "processed_webhook_updates",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("update_key", sa.String(length=160), nullable=False),
        sa.Column("update_type", sa.String(length=80), nullable=False),
        sa.Column("status", webhook_status, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_detail", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_processed_webhook_updates"),
        sa.UniqueConstraint(
            "update_key", name="uq_processed_webhook_updates_update_key"
        ),
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("status", sync_status, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chains_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "pokemon_processed", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("error_detail", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sync_runs"),
    )


def downgrade() -> None:
    op.drop_table("sync_runs")
    op.drop_table("processed_webhook_updates")
    op.drop_table("favorites")
    op.drop_table("user_collections")
    op.drop_index("ix_daily_deliveries_due", table_name="daily_deliveries")
    op.drop_table("daily_deliveries")
    op.drop_table("pokemon_abilities")
    op.drop_table("pokemon_types")
    op.drop_table("evolution_stages")
    op.drop_table("pokemon")
    op.drop_table("pokemon_species")
    op.drop_table("abilities")
    op.drop_table("types")
    op.drop_table("evolution_chains")
    op.drop_table("users")
    sync_status.drop(op.get_bind(), checkfirst=True)
    webhook_status.drop(op.get_bind(), checkfirst=True)
    delivery_status.drop(op.get_bind(), checkfirst=True)

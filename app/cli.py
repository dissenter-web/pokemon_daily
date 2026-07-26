import argparse
import asyncio
import json

from app.clients.max_api import MaxAPIClient
from app.clients.pokeapi import PokeAPIClient
from app.config import get_settings
from app.db.session import SessionFactory, engine
from app.logging_config import configure_logging
from app.services.catalog_sync import CatalogSyncService
from app.services.delivery import DeliveryService

UPDATE_TYPES = [
    "bot_started",
    "bot_stopped",
    "dialog_removed",
    "message_created",
    "message_callback",
]


async def sync_catalog(max_chains: int) -> None:
    settings = get_settings()
    async with (
        PokeAPIClient(
            base_url=settings.pokeapi_base_url,
            timeout_seconds=settings.pokeapi_timeout_seconds,
            request_delay_seconds=settings.pokeapi_request_delay_seconds,
        ) as client,
        SessionFactory() as session,
    ):
        result = await CatalogSyncService(
            session, client, settings.editorial_content_path
        ).run(max_chains=max_chains)
    print(json.dumps({"chains": result[0], "pokemon": result[1]}))


async def register_webhook() -> None:
    settings = get_settings()
    secret = settings.max_webhook_secret.get_secret_value()
    if not secret:
        raise SystemExit("MAX_WEBHOOK_SECRET is required")
    async with MaxAPIClient(
        token=settings.max_bot_token.get_secret_value(),
        base_url=settings.max_api_base_url,
        ca_bundle=settings.max_ca_bundle,
    ) as client:
        result = await client.register_webhook(
            url=settings.webhook_url,
            secret=secret,
            update_types=UPDATE_TYPES,
        )
    print(json.dumps(result, ensure_ascii=False))


async def delivery_run() -> None:
    settings = get_settings()
    async with (
        MaxAPIClient(
            token=settings.max_bot_token.get_secret_value(),
            base_url=settings.max_api_base_url,
            ca_bundle=settings.max_ca_bundle,
        ) as client,
        SessionFactory() as session,
    ):
        result = await DeliveryService(session, client, settings).run_due_batch()
    print(json.dumps({"planned": result.planned, "attempted": result.attempted}))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m app.cli")
    commands = root.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync-catalog")
    sync.add_argument(
        "--max-chains",
        type=int,
        default=0,
        help="0 means all chains; use 3 for the bundled nine-card starter catalog",
    )
    commands.add_parser("register-webhook")
    commands.add_parser("delivery-run")
    return root


async def async_main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    arguments = parser().parse_args()
    try:
        if arguments.command == "sync-catalog":
            await sync_catalog(max(arguments.max_chains, 0))
        elif arguments.command == "register-webhook":
            await register_webhook()
        elif arguments.command == "delivery-run":
            await delivery_run()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(async_main())


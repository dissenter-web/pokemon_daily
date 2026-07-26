import asyncio
import logging

from app.clients.max_api import MaxAPIClient
from app.config import get_settings
from app.db.session import SessionFactory, engine
from app.logging_config import configure_logging
from app.services.delivery import DeliveryService
from app.utils.time import delivery_time_reached, utc_now

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


async def run_worker() -> None:
    logger.info("delivery_worker_starting")
    async with MaxAPIClient(
        token=settings.max_bot_token.get_secret_value(),
        base_url=settings.max_api_base_url,
        ca_bundle=settings.max_ca_bundle,
    ) as max_client:
        while True:
            try:
                now = utc_now()
                if delivery_time_reached(
                    now,
                    settings.app_timezone,
                    settings.daily_delivery_time,
                ):
                    async with SessionFactory() as session:
                        result = await DeliveryService(
                            session, max_client, settings
                        ).run_due_batch()
                    logger.info(
                        "delivery_worker_cycle",
                        extra={
                            "planned": result.planned,
                            "attempted": result.attempted,
                        },
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("delivery_worker_cycle_failed")
            await asyncio.sleep(settings.worker_poll_seconds)


async def main() -> None:
    try:
        await run_worker()
    finally:
        await engine.dispose()
        logger.info("delivery_worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())


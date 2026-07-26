import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes import router
from app.clients.max_api import MaxAPIClient
from app.config import get_settings
from app.db.session import engine
from app.logging_config import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "application_starting",
        extra={"environment": settings.environment},
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as error:
        logger.exception("database_startup_check_failed")
        raise RuntimeError(
            "PostgreSQL is unavailable during application startup"
        ) from error
    async with MaxAPIClient(
        token=settings.max_bot_token.get_secret_value(),
        base_url=settings.max_api_base_url,
        ca_bundle=settings.max_ca_bundle,
    ) as max_client:
        app.state.max_client = max_client
        yield
    await engine.dispose()
    logger.info("application_stopped")


app = FastAPI(
    title="Pokemon Daily",
    version="1.0.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)
app.include_router(router)

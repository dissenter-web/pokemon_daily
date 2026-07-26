import hmac
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_max_client
from app.clients.max_api import MaxAPIClient
from app.config import Settings, get_settings
from app.db.session import get_session
from app.domain.errors import SafeRetryableMaxError
from app.schemas.max_api import MaxUpdate
from app.services.webhook import WebhookService

logger = logging.getLogger(__name__)
router = APIRouter()

SessionDependency = Annotated[AsyncSession, Depends(get_session)]
MaxClientDependency = Annotated[MaxAPIClient, Depends(get_max_client)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(session: SessionDependency) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as error:
        logger.exception("database_readiness_failed")
        raise HTTPException(status_code=503, detail="database unavailable") from error
    return {"status": "ready", "database": "ok"}


@router.post(get_settings().webhook_path)
async def max_webhook(
    request: Request,
    session: SessionDependency,
    max_client: MaxClientDependency,
    settings: SettingsDependency,
    x_max_bot_api_secret: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    expected_secret = settings.max_webhook_secret.get_secret_value()
    if expected_secret and (
        x_max_bot_api_secret is None
        or not hmac.compare_digest(x_max_bot_api_secret, expected_secret)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad secret")

    body = await request.body()
    if len(body) > settings.webhook_max_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="request body too large",
        )
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=400, detail="invalid JSON") from error

    raw_updates: list[dict[str, Any]]
    if isinstance(payload, dict) and isinstance(payload.get("updates"), list):
        raw_updates = payload["updates"]
    elif isinstance(payload, dict):
        raw_updates = [payload]
    else:
        raise HTTPException(status_code=400, detail="update must be an object")

    service = WebhookService(session, max_client, settings)
    processed = 0
    try:
        for raw_update in raw_updates:
            update = MaxUpdate.model_validate(raw_update)
            if await service.process(update):
                processed += 1
    except ValidationError as error:
        raise HTTPException(status_code=400, detail="invalid update") from error
    except SafeRetryableMaxError as error:
        raise HTTPException(status_code=503, detail="temporary MAX failure") from error
    return {"ok": True, "processed": processed}

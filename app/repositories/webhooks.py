from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProcessedWebhookUpdate
from app.domain.enums import WebhookStatus
from app.utils.time import utc_now


class WebhookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def claim(
        self, update_key: str, update_type: str, payload: dict
    ) -> bool:
        result = await self.session.execute(
            insert(ProcessedWebhookUpdate)
            .values(
                update_key=update_key,
                update_type=update_type,
                status=WebhookStatus.PROCESSING,
                payload=payload,
            )
            .on_conflict_do_nothing(
                index_elements=[ProcessedWebhookUpdate.update_key]
            )
            .returning(ProcessedWebhookUpdate.id)
        )
        return result.scalar_one_or_none() is not None

    async def mark_processed(self, update_key: str) -> None:
        await self.session.execute(
            update(ProcessedWebhookUpdate)
            .where(ProcessedWebhookUpdate.update_key == update_key)
            .values(status=WebhookStatus.PROCESSED, processed_at=utc_now())
        )

    async def mark_failed(self, update_key: str, detail: str) -> None:
        await self.session.execute(
            update(ProcessedWebhookUpdate)
            .where(ProcessedWebhookUpdate.update_key == update_key)
            .values(
                status=WebhookStatus.FAILED,
                processed_at=utc_now(),
                error_detail=detail[:500],
            )
        )

    async def release(self, update_key: str) -> None:
        await self.session.execute(
            delete(ProcessedWebhookUpdate).where(
                ProcessedWebhookUpdate.update_key == update_key,
                ProcessedWebhookUpdate.status == WebhookStatus.PROCESSING,
            )
        )

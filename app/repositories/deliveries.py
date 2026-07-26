from datetime import date, datetime

from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyDelivery, User, UserCollection
from app.domain.enums import DeliveryStatus


class DeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_day(self, user_id: int, delivery_date: date) -> DailyDelivery | None:
        result = await self.session.execute(
            select(DailyDelivery).where(
                DailyDelivery.user_id == user_id,
                DailyDelivery.delivery_date == delivery_date,
            )
        )
        return result.scalar_one_or_none()

    async def get_unresolved(self, user_id: int) -> DailyDelivery | None:
        result = await self.session.execute(
            select(DailyDelivery)
            .where(
                DailyDelivery.user_id == user_id,
                DailyDelivery.status.in_(
                    [
                        DeliveryStatus.PENDING,
                        DeliveryStatus.RETRYABLE,
                        DeliveryStatus.SENDING,
                    ]
                ),
            )
            .order_by(DailyDelivery.delivery_date, DailyDelivery.id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_pending(
        self,
        *,
        user_id: int,
        pokemon_id: int,
        delivery_date: date,
        scheduled_at: datetime,
    ) -> DailyDelivery:
        statement = (
            insert(DailyDelivery)
            .values(
                user_id=user_id,
                pokemon_id=pokemon_id,
                delivery_date=delivery_date,
                status=DeliveryStatus.PENDING,
                scheduled_at=scheduled_at,
                next_attempt_at=scheduled_at,
            )
            .on_conflict_do_nothing(
                index_elements=[DailyDelivery.user_id, DailyDelivery.delivery_date]
            )
            .returning(DailyDelivery.id)
        )
        await self.session.execute(statement)
        delivery = await self.get_for_day(user_id, delivery_date)
        if delivery is None:
            raise RuntimeError("daily delivery reservation was not created")
        return delivery

    async def due_ids(self, now: datetime, limit: int) -> list[int]:
        result = await self.session.execute(
            select(DailyDelivery.id)
            .join(User, User.id == DailyDelivery.user_id)
            .where(
                User.is_active.is_(True),
                DailyDelivery.status.in_(
                    [DeliveryStatus.PENDING, DeliveryStatus.RETRYABLE]
                ),
                DailyDelivery.next_attempt_at <= now,
            )
            .order_by(DailyDelivery.next_attempt_at, DailyDelivery.id)
            .limit(limit)
        )
        return list(result.scalars())

    async def claim(
        self, delivery_id: int, now: datetime, delivery_date: date
    ) -> DailyDelivery | None:
        result = await self.session.execute(
            update(DailyDelivery)
            .where(
                DailyDelivery.id == delivery_id,
                DailyDelivery.status.in_(
                    [DeliveryStatus.PENDING, DeliveryStatus.RETRYABLE]
                ),
                DailyDelivery.next_attempt_at <= now,
            )
            .values(
                status=DeliveryStatus.SENDING,
                attempted_at=now,
                attempt_count=DailyDelivery.attempt_count + 1,
                delivery_date=delivery_date,
                error_code=None,
                error_detail=None,
            )
            .returning(DailyDelivery)
        )
        return result.scalar_one_or_none()

    async def mark_sent(
        self,
        delivery: DailyDelivery,
        sent_at: datetime,
        max_message_id: str | None,
    ) -> None:
        await self.session.execute(
            insert(UserCollection)
            .values(
                user_id=delivery.user_id,
                pokemon_id=delivery.pokemon_id,
                delivery_id=delivery.id,
                obtained_at=sent_at,
            )
            .on_conflict_do_nothing(
                index_elements=[UserCollection.user_id, UserCollection.pokemon_id]
            )
        )
        await self.session.execute(
            update(DailyDelivery)
            .where(
                DailyDelivery.id == delivery.id,
                DailyDelivery.status == DeliveryStatus.SENDING,
            )
            .values(
                status=DeliveryStatus.SENT,
                sent_at=sent_at,
                max_message_id=max_message_id,
            )
        )

    async def mark_retryable(
        self,
        delivery_id: int,
        next_attempt_at: datetime,
        code: str,
        detail: str,
    ) -> None:
        await self.session.execute(
            update(DailyDelivery)
            .where(
                DailyDelivery.id == delivery_id,
                DailyDelivery.status == DeliveryStatus.SENDING,
            )
            .values(
                status=DeliveryStatus.RETRYABLE,
                next_attempt_at=next_attempt_at,
                error_code=code,
                error_detail=detail[:500],
            )
        )

    async def mark_permanently_failed(
        self, delivery_id: int, code: str, detail: str
    ) -> None:
        await self.session.execute(
            update(DailyDelivery)
            .where(
                DailyDelivery.id == delivery_id,
                DailyDelivery.status == DeliveryStatus.SENDING,
            )
            .values(
                status=DeliveryStatus.PERMANENTLY_FAILED,
                error_code=code,
                error_detail=detail[:500],
            )
        )

    async def quarantine_stale_sending(self, older_than: datetime) -> int:
        result = await self.session.execute(
            update(DailyDelivery)
            .where(
                DailyDelivery.status == DeliveryStatus.SENDING,
                and_(
                    DailyDelivery.attempted_at.is_not(None),
                    DailyDelivery.attempted_at < older_than,
                ),
            )
            .values(
                status=DeliveryStatus.PERMANENTLY_FAILED,
                error_code="ambiguous_worker_interruption",
                error_detail=(
                    "Worker stopped while MAX request could have been in flight; "
                    "automatic retry disabled to prevent a duplicate card"
                ),
            )
        )
        return result.rowcount or 0

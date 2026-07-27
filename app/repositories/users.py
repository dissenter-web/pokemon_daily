from datetime import date

from sqlalchemy import exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyDelivery, User
from app.domain.enums import DeliveryStatus
from app.utils.time import utc_now


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, max_user_id: int, max_chat_id: int | None) -> User:
        values = {
            "max_user_id": max_user_id,
            "max_chat_id": max_chat_id,
            "is_active": True,
            "last_interaction_at": utc_now(),
        }
        statement = insert(User).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[User.max_user_id],
            set_={
                "max_chat_id": statement.excluded.max_chat_id,
                "is_active": True,
                "last_interaction_at": statement.excluded.last_interaction_at,
            },
        )
        await self.session.execute(statement)
        result = await self.session.execute(
            select(User).where(User.max_user_id == max_user_id)
        )
        return result.scalar_one()

    async def lock(self, user_id: int) -> User:
        result = await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one()

    async def deactivate(self, max_user_id: int) -> None:
        user_id = (
            await self.session.execute(
                select(User.id).where(User.max_user_id == max_user_id)
            )
        ).scalar_one_or_none()
        if user_id is None:
            return
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_active=False, last_interaction_at=utc_now())
        )
        await self.session.execute(
            update(DailyDelivery)
            .where(
                DailyDelivery.user_id == user_id,
                DailyDelivery.status.in_(
                    [
                        DeliveryStatus.PENDING,
                        DeliveryStatus.RETRYABLE,
                    ]
                ),
            )
            .values(
                status=DeliveryStatus.PERMANENTLY_FAILED,
                error_code="user_inactive",
                error_detail="Delivery cancelled because the user stopped the bot",
            )
        )

    async def active_batch(self, limit: int, offset: int = 0) -> list[User]:
        result = await self.session.execute(
            select(User)
            .where(User.is_active.is_(True))
            .order_by(User.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars())

    async def active_without_delivery(
        self, delivery_date: date, limit: int
    ) -> list[User]:
        has_unresolved = (
            exists()
            .where(
                DailyDelivery.user_id == User.id,
                DailyDelivery.status.in_(
                    [
                        DeliveryStatus.PENDING,
                        DeliveryStatus.RETRYABLE,
                        DeliveryStatus.SENDING,
                    ]
                ),
            )
            .correlate(User)
        )
        
        result = await self.session.execute(
            select(User)
            .outerjoin(
                DailyDelivery,
                (DailyDelivery.user_id == User.id)
                & (DailyDelivery.delivery_date == delivery_date),
            )
            .where(
                User.is_active.is_(True),
                DailyDelivery.id.is_(None),
                ~has_unresolved,
            )
            .order_by(User.id)
            .limit(limit)
        )
        return list(result.scalars())

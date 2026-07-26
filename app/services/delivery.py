import logging
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.buttons import card_buttons, main_menu_buttons
from app.bot.formatter import format_card
from app.clients.max_api import MaxAPIClient
from app.config import Settings
from app.db.models import DailyDelivery, User
from app.domain.enums import DeliveryStatus
from app.domain.errors import (
    AmbiguousMaxError,
    CollectionCompleteError,
    PermanentMaxError,
    SafeRetryableMaxError,
)
from app.repositories.catalog import CatalogRepository
from app.repositories.collections import CollectionRepository
from app.repositories.deliveries import DeliveryRepository
from app.repositories.users import UserRepository
from app.services.delivery_policy import retry_delay_seconds
from app.utils.time import local_date, utc_now

logger = logging.getLogger(__name__)


class ManualDeliveryResult(StrEnum):
    SENT = "sent"
    ALREADY_SENT = "already_sent"
    IN_PROGRESS = "in_progress"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class BatchResult:
    planned: int
    attempted: int


class DeliveryService:
    def __init__(
        self,
        session: AsyncSession,
        max_client: MaxAPIClient,
        settings: Settings,
    ) -> None:
        self.session = session
        self.max_client = max_client
        self.settings = settings
        self.deliveries = DeliveryRepository(session)
        self.catalog = CatalogRepository(session)
        self.users = UserRepository(session)

    async def reserve_for_user(self, user: User) -> DailyDelivery:
        now = utc_now()
        day = local_date(now, self.settings.app_timezone)
        await self.users.lock(user.id)
        existing = await self.deliveries.get_for_day(user.id, day)
        if existing is not None:
            await self.session.commit()
            return existing
        unresolved = await self.deliveries.get_unresolved(user.id)
        if unresolved is not None:
            await self.session.commit()
            return unresolved
        pokemon = await self.catalog.next_for_user(user.id)
        if pokemon is None:
            raise CollectionCompleteError
        delivery = await self.deliveries.create_pending(
            user_id=user.id,
            pokemon_id=pokemon.id,
            delivery_date=day,
            scheduled_at=now,
        )
        await self.session.commit()
        return delivery

    async def deliver_manually(self, user: User) -> ManualDeliveryResult:
        try:
            delivery = await self.reserve_for_user(user)
        except CollectionCompleteError:
            await self.max_client.send_message(
                max_user_id=user.max_user_id,
                text=(
                    "<b>Коллекция собрана</b>\n\n"
                    "Все доступные карточки уже открыты. Новые появятся после "
                    "следующего обновления каталога."
                ),
                buttons=main_menu_buttons(),
            )
            return ManualDeliveryResult.COMPLETE

        if delivery.status == DeliveryStatus.SENT:
            await self.max_client.send_message(
                max_user_id=user.max_user_id,
                text=(
                    "Сегодняшний покемон уже получен. Следующая новая карточка "
                    "будет доступна в следующие календарные сутки."
                ),
                buttons=main_menu_buttons(),
            )
            return ManualDeliveryResult.ALREADY_SENT
        if delivery.status == DeliveryStatus.SENDING:
            await self.max_client.send_message(
                max_user_id=user.max_user_id,
                text="Карточка уже отправляется. Повторное нажатие не создаст новую.",
                buttons=main_menu_buttons(),
            )
            return ManualDeliveryResult.IN_PROGRESS
        if (
            delivery.status == DeliveryStatus.RETRYABLE
            and delivery.next_attempt_at > utc_now()
        ):
            await self.max_client.send_message(
                max_user_id=user.max_user_id,
                text=(
                    "MAX временно не принял карточку. Безопасный повтор уже "
                    "запланирован; новый покемон не будет пропущен."
                ),
                buttons=main_menu_buttons(),
            )
            return ManualDeliveryResult.RETRY_SCHEDULED
        if delivery.status == DeliveryStatus.PERMANENTLY_FAILED:
            await self.max_client.send_message(
                max_user_id=user.max_user_id,
                text=(
                    "Отправка сегодняшней карточки завершилась неопределённо. "
                    "Автоматический повтор отключён, чтобы не прислать дубль."
                ),
                buttons=main_menu_buttons(),
            )
            return ManualDeliveryResult.FAILED
        sent = await self.deliver_reserved(delivery.id)
        return (
            ManualDeliveryResult.SENT
            if sent
            else ManualDeliveryResult.RETRY_SCHEDULED
        )

    async def deliver_reserved(self, delivery_id: int) -> bool:
        now = utc_now()
        day = local_date(now, self.settings.app_timezone)
        delivery = await self.deliveries.claim(delivery_id, now, day)
        if delivery is None:
            await self.session.rollback()
            return False
        await self.session.commit()

        user = (
            await self.session.execute(select(User).where(User.id == delivery.user_id))
        ).scalar_one()
        if not user.is_active:
            await self.deliveries.mark_permanently_failed(
                delivery.id,
                "user_inactive",
                "Delivery cancelled because the user stopped the bot",
            )
            await self.session.commit()
            return False
        card = await self.catalog.card(delivery.pokemon_id)
        favorite = await CollectionRepository(self.session).is_favorite(
            user.id, delivery.pokemon_id
        )
        try:
            message_id = await self.max_client.send_message(
                max_user_id=user.max_user_id,
                text=format_card(card),
                buttons=card_buttons(card.pokemon_id, favorite),
                image_url=card.image_url,
            )
        except SafeRetryableMaxError as error:
            delay = retry_delay_seconds(
                attempt_count=delivery.attempt_count,
                retry_limit=self.settings.delivery_retry_limit,
                provider_retry_after=error.retry_after_seconds,
            )
            if delay is None:
                await self.deliveries.mark_permanently_failed(
                    delivery.id, "retry_limit", str(error)
                )
            else:
                await self.deliveries.mark_retryable(
                    delivery.id,
                    utc_now() + timedelta(seconds=delay),
                    "safe_retryable_max_error",
                    str(error),
                )
            await self.session.commit()
            logger.warning(
                "daily_delivery_retry_scheduled",
                extra={
                    "delivery_id": delivery.id,
                    "attempt": delivery.attempt_count,
                },
            )
            return False
        except AmbiguousMaxError as error:
            await self.deliveries.mark_permanently_failed(
                delivery.id, "ambiguous_max_result", str(error)
            )
            await self.session.commit()
            logger.error(
                "daily_delivery_ambiguous_result",
                extra={"delivery_id": delivery.id},
            )
            return False
        except PermanentMaxError as error:
            await self.deliveries.mark_permanently_failed(
                delivery.id, "permanent_max_error", str(error)
            )
            await self.session.commit()
            logger.error(
                "daily_delivery_permanent_failure",
                extra={"delivery_id": delivery.id},
            )
            return False

        sent_at = utc_now()
        await self.deliveries.mark_sent(delivery, sent_at, message_id)
        await self.session.commit()
        logger.info(
            "daily_delivery_sent",
            extra={
                "delivery_id": delivery.id,
                "user_id": user.id,
                "pokemon_id": delivery.pokemon_id,
            },
        )
        return True

    async def plan_due_users(self) -> int:
        now = utc_now()
        day = local_date(now, self.settings.app_timezone)
        users = await self.users.active_without_delivery(
            day, self.settings.delivery_batch_size
        )
        planned = 0
        for user in users:
            try:
                await self.reserve_for_user(user)
            except CollectionCompleteError:
                await self.session.rollback()
            else:
                planned += 1
        return planned

    async def run_due_batch(self) -> BatchResult:
        now = utc_now()
        stale_before = now - timedelta(minutes=self.settings.sending_stale_minutes)
        quarantined = await self.deliveries.quarantine_stale_sending(stale_before)
        if quarantined:
            logger.error(
                "stale_deliveries_quarantined",
                extra={"count": quarantined},
            )
        await self.session.commit()

        planned = await self.plan_due_users()
        ids = await self.deliveries.due_ids(utc_now(), self.settings.delivery_batch_size)
        attempted = 0
        for delivery_id in ids:
            await self.deliver_reserved(delivery_id)
            attempted += 1
        return BatchResult(planned=planned, attempted=attempted)

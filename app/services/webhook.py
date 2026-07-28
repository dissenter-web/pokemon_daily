import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.buttons import (
    callback_button,
    card_buttons,
    main_menu_buttons,
    pagination_buttons,
)
from app.bot.formatter import (
    format_about,
    format_card,
    format_collection,
    format_main_menu,
    format_statistics,
)
from app.clients.max_api import MaxAPIClient
from app.config import Settings
from app.domain.errors import (
    AmbiguousMaxError,
    PermanentMaxError,
    SafeRetryableMaxError,
)
from app.repositories.users import UserRepository
from app.repositories.webhooks import WebhookRepository
from app.schemas.max_api import MaxUpdate
from app.services.collection import CollectionService
from app.services.delivery import DeliveryService

logger = logging.getLogger(__name__)


class WebhookService:
    def __init__(
        self,
        session: AsyncSession,
        max_client: MaxAPIClient,
        settings: Settings,
    ) -> None:
        self.session = session
        self.max_client = max_client
        self.settings = settings
        self.webhooks = WebhookRepository(session)
        self.users = UserRepository(session)
        self.collections = CollectionService(session, settings.collection_page_size)

    async def process(self, update: MaxUpdate) -> bool:
        payload = update.model_dump(mode="json")
        claimed = await self.webhooks.claim(
            update.stable_key, update.update_type, payload
        )
        await self.session.commit()
        if not claimed:
            logger.info(
                "duplicate_webhook_update",
                extra={"update_type": update.update_type},
            )
            return False

        try:
            await self._dispatch(update)
        except SafeRetryableMaxError:
            await self.webhooks.release(update.stable_key)
            await self.session.commit()
            raise
        except (AmbiguousMaxError, PermanentMaxError) as error:
            await self.webhooks.mark_failed(update.stable_key, str(error))
            await self.session.commit()
            logger.error(
                "webhook_side_effect_failed",
                extra={"update_type": update.update_type},
            )
            return True
        except Exception as error:
            await self.session.rollback()
            await self.webhooks.mark_failed(update.stable_key, str(error))
            await self.session.commit()
            raise
        else:
            await self.webhooks.mark_processed(update.stable_key)
            await self.session.commit()
            logger.info(
                "webhook_update_processed",
                extra={"update_type": update.update_type},
            )
            return True

    async def _dispatch(self, update: MaxUpdate) -> None:
        max_user_id = update.max_user_id
        if max_user_id is None:
            logger.info(
                "webhook_without_direct_user_ignored",
                extra={"update_type": update.update_type},
            )
            return

        if update.update_type in {"bot_stopped", "dialog_removed"}:
            await self.users.deactivate(max_user_id)
            await self.session.commit()
            return

        user = await self.users.get_or_create(max_user_id, update.max_chat_id)
        await self.session.commit()

        if update.update_type in {"bot_started", "message_created"}:
            await self.max_client.send_message(
                max_user_id=max_user_id,
                text=format_main_menu(),
                buttons=main_menu_buttons(),
            )
            return

        if update.update_type != "message_callback":
            return
        logger.info(
            "callback_routed",
            extra={
                "action": (update.callback_payload or "menu").split(":", 1)[0]
            },
        )
        await self._callback(user, update.callback_payload)

    async def _callback(self, user, payload: str | None) -> None:
        if not payload or len(payload) > 128:
            payload = "menu"
        parts = payload.split(":")
        action = parts[0]

        if payload == "menu":
            await self.max_client.send_message(
                max_user_id=user.max_user_id,
                text=format_main_menu(),
                buttons=main_menu_buttons(),
            )
            return
        if payload == "daily:get":
            delivery = DeliveryService(self.session, self.max_client, self.settings)
            await delivery.deliver_manually(user)
            return
        if action in {"collection", "favorites"}:
            page = self._positive_integer(parts[1] if len(parts) > 1 else "0") or 0
            favorites_only = action == "favorites"
            collection_page = await self.collections.page(
                user.id, page, favorites_only=favorites_only
            )
            await self.max_client.send_message(
                max_user_id=user.max_user_id,
                text=format_collection(
                    collection_page,
                    "Избранное" if favorites_only else "Коллекция",
                ),
                buttons=pagination_buttons(
                    prefix=action,
                    page=collection_page.page,
                    total_pages=collection_page.total_pages,
                ),
            )
            return
        if action == "favorite" and len(parts) == 3:
            favorite = parts[1] == "add"
            pokemon_id = self._positive_integer(parts[2])
            if pokemon_id is None or parts[1] not in {"add", "remove"}:
                return
            changed = await self.collections.set_favorite(
                user.id, pokemon_id, favorite=favorite
            )
            if not changed:
                text = "Сначала откройте этого покемона в своей коллекции."
                buttons = main_menu_buttons()
            else:
                card, is_favorite = await self.collections.card(user.id, pokemon_id)
                text = format_card(card)
                buttons = card_buttons(card.pokemon_id, is_favorite)
            await self.max_client.send_message(
                max_user_id=user.max_user_id,
                text=text,
                buttons=buttons,
            )
            return
        if payload == "stats":
            statistics = await self.collections.statistics(user)
            await self.max_client.send_message(
                max_user_id=user.max_user_id,
                text=format_statistics(statistics),
                buttons=[[callback_button("Главное меню", "menu")]],
            )
            return
        if payload == "about":
            await self.max_client.send_message(
                max_user_id=user.max_user_id,
                text=format_about(),
                buttons=[[callback_button("Главное меню", "menu")]],
            )
            return

        await self.max_client.send_message(
            max_user_id=user.max_user_id,
            text=format_main_menu(),
            buttons=main_menu_buttons(),
        )

    @staticmethod
    def _positive_integer(value: str) -> int | None:
        if not value.isdigit():
            return None
        parsed = int(value)
        return parsed if 0 <= parsed <= 9_223_372_036_854_775_807 else None

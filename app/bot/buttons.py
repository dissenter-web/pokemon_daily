import re
from collections.abc import Sequence

PAYLOAD_PATTERN = re.compile(r"^[a-z0-9:._-]{1,128}$")


def callback_button(text: str, payload: str) -> dict[str, str]:
    if not PAYLOAD_PATTERN.fullmatch(payload):
        raise ValueError(f"unsafe callback payload: {payload!r}")
    return {"type": "callback", "text": text[:80], "payload": payload}


def main_menu_buttons() -> list[list[dict[str, str]]]:
    return [
        [callback_button("🎁 Получить покемона", "daily:get")],
        [callback_button("📚 Коллекция", "collection:0")],
        [callback_button("📊 Статистика", "stats")],
        [callback_button("ℹ️ О проекте", "about")],
    ]


def card_buttons(pokemon_id: int, is_favorite: bool) -> list[list[dict[str, str]]]:
    favorite = (
        callback_button("Убрать из избранного", f"favorite:remove:{pokemon_id}")
        if is_favorite
        else callback_button("В избранное", f"favorite:add:{pokemon_id}")
    )
    return [[favorite], [callback_button("Главное меню", "menu")]]


def pagination_buttons(
    *,
    prefix: str,
    page: int,
    total_pages: int,
) -> list[list[dict[str, str]]]:
    row: list[dict[str, str]] = []
    if page > 0:
        row.append(callback_button("← Назад", f"{prefix}:{page - 1}"))
    if page + 1 < total_pages:
        row.append(callback_button("Вперёд →", f"{prefix}:{page + 1}"))
    result: list[list[dict[str, str]]] = []
    if row:
        result.append(row)
    result.append([callback_button("Главное меню", "menu")])
    return result


def rows(*groups: Sequence[dict[str, str]]) -> list[list[dict[str, str]]]:
    return [list(group) for group in groups]


from html import escape

from app.domain.entities import CollectionPage, PokemonCard, UserStatistics


def format_main_menu() -> str:
    return (
        "<b>Pokémon Daily</b>\n\n"
        "Каждый день — новый покемон по порядку его эволюционной цепочки. "
        "Выберите раздел:"
    )


def format_card(card: PokemonCard) -> str:
    evolution = []

    for index, name in enumerate(card.evolution_names):
        escaped_name = escape(name)

        if index == card.evolution_index:
            evolution.append(f"<b>{escaped_name}</b>")
        else:
            evolution.append(escaped_name)

    types = ", ".join(
        escape(value) for value in card.types
    ) or "не указаны"

    abilities = ", ".join(
        escape(value) for value in card.abilities
    ) or "не указаны"

    return (
        f"✨ <b>{escape(card.name_ru)}</b>\n"
        f"<i>{escape(card.name_en)} · #{card.pokedex_number:04d}</i>\n\n"

        f"🔹 <b>Тип:</b> {types}\n"
        f"⚡ <b>Способности:</b> {abilities}\n\n"

        f"📖 <b>Описание</b>\n"
        f"{escape(card.description_ru)}\n\n"

        f"💡 <b>Интересный факт</b>\n"
        f"{escape(card.fact_ru)}\n\n"

        f"🧬 <b>Эволюция</b>\n"
        f"{' → '.join(evolution)}"
    )


def format_collection(page: CollectionPage, title: str) -> str:
    if not page.items:
        return f"<b>{escape(title)}</b>\n\nЗдесь пока пусто."
    lines = [f"<b>{escape(title)}</b>", ""]
    for item in page.items:
        lines.append(
            f"#{item.pokedex_number:04d} <b>{escape(item.name_ru)}</b> "
            f"(<i>{escape(item.name_en)}</i>)"
        )
    lines.extend(
        [
            "",
            f"Страница {page.page + 1} из {page.total_pages} · "
            f"Всего: {page.total_items}",
        ]
    )
    return "\n".join(lines)


def format_statistics(statistics: UserStatistics) -> str:
    started = statistics.started_at.strftime("%d.%m.%Y")
    last = (
        statistics.last_received_at.strftime("%d.%m.%Y")
        if statistics.last_received_at
        else "ещё не было"
    )
    chain = str(statistics.current_chain) if statistics.current_chain is not None else "—"
    stage = (
        str(statistics.current_stage + 1)
        if statistics.current_stage is not None
        else "—"
    )
    return (
        "<b>Статистика</b>\n\n"
        f"Открыто: <b>{statistics.opened}</b> из {statistics.available} "
        f"({statistics.completion_percent}%)\n"
        f"В избранном: <b>{statistics.favorites}</b>\n"
        f"С нами с: <b>{started}</b>\n"
        f"Последняя карточка: <b>{last}</b>\n"
        f"Текущая цепочка: <b>{chain}</b>\n"
        f"Этап внутри цепочки: <b>{stage}</b>\n"
        f"Успешных доставок: <b>{statistics.successful_deliveries}</b>"
    )


def format_about() -> str:
    return (
        "<b>О проекте</b>\n\n"
        "Pokémon Daily — некоммерческий семейный учебный проект. "
        "Данные каталога синхронизируются из PokéAPI, а русские описания "
        "редактируются и хранятся локально.\n\n"
        "Проект не связан с Nintendo, Game Freak или The Pokémon Company. "
        "Названия Pokémon и персонажей принадлежат их правообладателям."
    )


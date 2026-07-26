from app.bot.formatter import format_card
from app.domain.entities import PokemonCard


def test_card_escapes_external_text_and_marks_current_evolution() -> None:
    card = PokemonCard(
        pokemon_id=1,
        pokedex_number=1,
        name_ru="<Бульбазавр>",
        name_en="Bulbasaur",
        description_ru="Seed & plant",
        fact_ru="Safe",
        image_url=None,
        types=("Трава", "Яд"),
        abilities=("Зарастание",),
        evolution_names=("Бульбазавр", "Ивизавр", "Венузавр"),
        evolution_index=1,
    )
    text = format_card(card)
    assert "&lt;Бульбазавр&gt;" in text
    assert "Seed &amp; plant" in text
    assert "<b>Ивизавр</b>" in text


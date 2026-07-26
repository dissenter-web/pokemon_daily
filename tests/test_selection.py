from app.services.selection import first_uncollected


def test_selects_in_deterministic_evolution_order() -> None:
    ordered = [1, 2, 3, 4, 5, 6]
    assert first_uncollected(ordered, []) == 1
    assert first_uncollected(ordered, [1]) == 2
    assert first_uncollected(ordered, [1, 2, 3]) == 4


def test_never_repeats_collected_pokemon() -> None:
    assert first_uncollected([1, 2, 3], [1, 3]) == 2


def test_returns_none_when_collection_complete() -> None:
    assert first_uncollected([1, 2, 3], [3, 2, 1]) is None


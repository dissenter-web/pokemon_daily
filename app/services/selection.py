from collections.abc import Iterable, Sequence


def first_uncollected(
    ordered_pokemon_ids: Sequence[int], collected_ids: Iterable[int]
) -> int | None:
    collected = set(collected_ids)
    return next(
        (pokemon_id for pokemon_id in ordered_pokemon_ids if pokemon_id not in collected),
        None,
    )


from sqlalchemy import UniqueConstraint

from app.db.models import DailyDelivery, Favorite, User, UserCollection


def unique_columns(model) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_database_enforces_one_delivery_per_calendar_day() -> None:
    assert ("user_id", "delivery_date") in unique_columns(DailyDelivery)


def test_database_enforces_no_collection_or_favorite_duplicates() -> None:
    assert ("user_id", "pokemon_id") in unique_columns(UserCollection)
    assert ("user_id", "pokemon_id") in unique_columns(Favorite)


def test_database_enforces_unique_max_user() -> None:
    assert User.__table__.c.max_user_id.unique is True


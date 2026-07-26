import pytest

from app.bot.buttons import callback_button, pagination_buttons


def test_callback_payload_is_restricted() -> None:
    assert callback_button("OK", "favorite:add:42")["payload"] == "favorite:add:42"
    with pytest.raises(ValueError):
        callback_button("Bad", "../../secret")
    with pytest.raises(ValueError):
        callback_button("Bad", "x" * 129)


def test_pagination_has_no_out_of_range_buttons() -> None:
    first = pagination_buttons(prefix="collection", page=0, total_pages=3)
    assert [button["payload"] for button in first[0]] == ["collection:1"]
    last = pagination_buttons(prefix="collection", page=2, total_pages=3)
    assert [button["payload"] for button in last[0]] == ["collection:1"]


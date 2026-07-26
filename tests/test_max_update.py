from app.schemas.max_api import MaxUpdate


def test_extracts_callback_user_payload_and_stable_key() -> None:
    payload = {
        "update_type": "message_callback",
        "timestamp": 123,
        "callback": {
            "callback_id": "callback-1",
            "payload": "stats",
            "user": {"user_id": 777},
        },
        "message": {"recipient": {"chat_id": 888}},
    }
    first = MaxUpdate.model_validate(payload)
    second = MaxUpdate.model_validate(payload)
    assert first.max_user_id == 777
    assert first.max_chat_id == 888
    assert first.callback_payload == "stats"
    assert first.stable_key == second.stable_key


def test_different_message_ids_are_not_duplicates() -> None:
    first_payload = {
        "update_type": "message_created",
        "timestamp": 123,
        "message": {
            "sender": {"user_id": 777},
            "body": {"mid": "one", "text": "hello"},
        },
    }
    second_payload = {
        "update_type": "message_created",
        "timestamp": 123,
        "message": {
            "sender": {"user_id": 777},
            "body": {"mid": "two", "text": "hello"},
        },
    }
    first = MaxUpdate.model_validate(first_payload)
    second = MaxUpdate.model_validate(second_payload)
    assert first.stable_key != second.stable_key


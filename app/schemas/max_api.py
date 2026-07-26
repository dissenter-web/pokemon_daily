import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MaxUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    update_type: str = Field(min_length=1, max_length=80)
    timestamp: int = Field(ge=0)
    chat_id: int | None = None
    user: dict[str, Any] | None = None
    message: dict[str, Any] | None = None
    callback: dict[str, Any] | None = None

    @staticmethod
    def _integer(value: Any) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    @property
    def max_user_id(self) -> int | None:
        candidates = [
            (self.user or {}).get("user_id"),
            ((self.callback or {}).get("user") or {}).get("user_id"),
            ((self.message or {}).get("sender") or {}).get("user_id"),
        ]
        for candidate in candidates:
            parsed = self._integer(candidate)
            if parsed is not None:
                return parsed
        return None

    @property
    def max_chat_id(self) -> int | None:
        candidates = [
            self.chat_id,
            ((self.message or {}).get("recipient") or {}).get("chat_id"),
            (self.message or {}).get("chat_id"),
        ]
        for candidate in candidates:
            parsed = self._integer(candidate)
            if parsed is not None:
                return parsed
        return None

    @property
    def callback_payload(self) -> str | None:
        value = (self.callback or {}).get("payload")
        return value if isinstance(value, str) else None

    @property
    def callback_id(self) -> str | None:
        value = (self.callback or {}).get("callback_id")
        return str(value) if value is not None else None

    @property
    def message_text(self) -> str | None:
        body = (self.message or {}).get("body") or {}
        value = body.get("text")
        return value if isinstance(value, str) else None

    @property
    def stable_key(self) -> str:
        body = (self.message or {}).get("body") or {}
        message_id = body.get("mid") or (self.message or {}).get("mid")
        event_id = self.callback_id or message_id
        if event_id is not None:
            raw = f"{self.update_type}:{event_id}"
        else:
            canonical = json.dumps(
                self.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            raw = f"{self.update_type}:{self.timestamp}:{canonical}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"{self.update_type}:{digest}"


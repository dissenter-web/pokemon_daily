from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://pokemon_daily:change_me@localhost/pokemon_daily"

    app_timezone: str = "Europe/Moscow"
    daily_delivery_time: str = "08:00"
    worker_poll_seconds: int = Field(default=60, ge=10, le=3600)
    delivery_batch_size: int = Field(default=50, ge=1, le=500)
    delivery_retry_limit: int = Field(default=4, ge=1, le=10)
    sending_stale_minutes: int = Field(default=15, ge=5, le=1440)
    collection_page_size: int = Field(default=5, ge=1, le=20)

    max_bot_token: SecretStr = SecretStr("")
    max_webhook_secret: SecretStr = SecretStr("")
    max_api_base_url: str = "https://platform-api2.max.ru"
    max_ca_bundle: Path = Path("/etc/ssl/certs/ca-certificates.crt")
    public_base_url: str = "https://bot.example.com"
    webhook_path: str = "/webhook/max"
    webhook_max_body_bytes: int = Field(default=262_144, ge=1024, le=1_048_576)

    pokeapi_base_url: str = "https://pokeapi.co/api/v2"
    pokeapi_timeout_seconds: float = Field(default=20.0, ge=2, le=120)
    pokeapi_request_delay_seconds: float = Field(default=0.05, ge=0, le=5)
    editorial_content_path: Path = Path("data/editorial")

    @field_validator("daily_delivery_time")
    @classmethod
    def validate_delivery_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("DAILY_DELIVERY_TIME must use HH:MM")
        hour, minute = (int(part) for part in parts)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("DAILY_DELIVERY_TIME contains invalid time")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("webhook_path")
    @classmethod
    def validate_webhook_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("WEBHOOK_PATH must start with /")
        return value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> Settings:
        secret = self.max_webhook_secret.get_secret_value()
        token = self.max_bot_token.get_secret_value()
        if secret and not re.fullmatch(r"[A-Za-z0-9_-]{5,256}", secret):
            raise ValueError("MAX_WEBHOOK_SECRET must match [A-Za-z0-9_-]{5,256}")
        if self.environment == "production":
            if not token:
                raise ValueError("MAX_BOT_TOKEN is required in production")
            if not secret:
                raise ValueError("MAX_WEBHOOK_SECRET is required in production")
            if not self.public_base_url.startswith("https://"):
                raise ValueError("PUBLIC_BASE_URL must use HTTPS in production")
        return self

    @computed_field
    @property
    def webhook_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}{self.webhook_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()

from enum import StrEnum


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    RETRYABLE = "retryable"
    PERMANENTLY_FAILED = "permanently_failed"


class WebhookStatus(StrEnum):
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class SyncStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


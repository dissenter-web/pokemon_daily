class MaxAPIError(RuntimeError):
    """Base error for the MAX API boundary."""


class SafeRetryableMaxError(MaxAPIError):
    """The request definitely did not produce the intended side effect."""

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class AmbiguousMaxError(MaxAPIError):
    """MAX might have accepted the request, therefore automatic retry is unsafe."""


class PermanentMaxError(MaxAPIError):
    """The request must be changed before a retry can succeed."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CollectionCompleteError(RuntimeError):
    """No unopened editorial-ready Pokemon remains."""

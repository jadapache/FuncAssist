"""Typed AI errors with structured codes and user-friendly messages."""

from __future__ import annotations


class AIError(Exception):
    """Base typed exception for AI provider and runner failures."""

    def __init__(
        self,
        code: str,
        user_message: str,
        retry_after: float | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.retry_after = retry_after
        self.original_error = original_error

    def to_dict(self) -> dict[str, str | float | None]:
        return {
            "code": self.code,
            "message": self.user_message,
            "retry_after": self.retry_after,
        }

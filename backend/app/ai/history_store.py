"""Database-backed SummaryStore for rolling conversation summaries."""

from __future__ import annotations

from app.db.unit_of_work import AsyncUnitOfWork


class ChatSessionSummaryStore:
    """Persists the rolling summary on `chat_sessions` for one conversation.

    Each operation uses its own unit of work with an explicit commit, so it does not depend on
    the request-scoped session (which may already be closed while a streaming response runs).
    """

    def __init__(self, session_id: str, user_id: str | None = None) -> None:
        self.session_id = session_id
        self.user_id = user_id

    async def load(self) -> tuple[str, str] | None:
        async with AsyncUnitOfWork() as uow:
            return await uow.chat.get_history_summary(self.session_id, user_id=self.user_id)

    async def save(self, summary_key: str, summary: str) -> None:
        async with AsyncUnitOfWork() as uow:
            if await uow.chat.save_history_summary(self.session_id, summary_key, summary, user_id=self.user_id):
                await uow.commit()

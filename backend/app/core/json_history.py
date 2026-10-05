"""JSON-based history storage for chat, standups, PRD reviews, and test plans."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from pathlib import Path

from app.core.settings import HISTORY_DIR


def _get_history_file(name: str) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return HISTORY_DIR / f"{name}.json"


def _load_history(name: str) -> List[dict[str, Any]]:
    path = _get_history_file(name)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_history(name: str, items: List[dict[str, Any]]) -> None:
    path = _get_history_file(name)
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


class JsonChatRepository:
    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        context_sources: Optional[List[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        messages = _load_history(f"chat_{session_id}")
        msg = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "role": role,
            "content": content,
            "context_sources": context_sources or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        messages.append(msg)
        _save_history(f"chat_{session_id}", messages)
        return msg

    async def get_session_messages(
        self, session_id: str, limit: int = 50
    ) -> List[dict[str, Any]]:
        messages = _load_history(f"chat_{session_id}")
        return messages[-limit:] if limit > 0 else messages

    async def clear_session(self, session_id: str) -> bool:
        _save_history(f"chat_{session_id}", [])
        return True


class JsonStandupRepository:
    async def create_standup(
        self, title: str, content: str, sources: Optional[List[str]] = None
    ) -> dict[str, Any]:
        items = _load_history("standups")
        item = {
            "id": str(uuid.uuid4()),
            "title": title,
            "content": content,
            "sources": sources or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        items.insert(0, item)
        _save_history("standups", items)
        return item

    async def get_all_standups(self, limit: int = 20) -> List[dict[str, Any]]:
        items = _load_history("standups")
        return items[:limit]


class JsonPRDRepository:
    async def create_prd_review(
        self, prd_title: str, content: str
    ) -> dict[str, Any]:
        items = _load_history("prd_reviews")
        item = {
            "id": str(uuid.uuid4()),
            "prd_title": prd_title,
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        items.insert(0, item)
        _save_history("prd_reviews", items)
        return item

    async def get_all_prd_reviews(self, limit: int = 20) -> List[dict[str, Any]]:
        items = _load_history("prd_reviews")
        return items[:limit]


class JsonTestPlanRepository:
    async def create_test_plan(
        self, feature_name: str, content: str, test_type: str = "general"
    ) -> dict[str, Any]:
        items = _load_history("test_plans")
        item = {
            "id": str(uuid.uuid4()),
            "feature_name": feature_name,
            "content": content,
            "test_type": test_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        items.insert(0, item)
        _save_history("test_plans", items)
        return item

    async def get_all_test_plans(self, limit: int = 20) -> List[dict[str, Any]]:
        items = _load_history("test_plans")
        return items[:limit]

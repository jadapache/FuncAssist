"""Tests verifying total removal of SQLite and JSON persistence across the application."""

import sys
import pytest
from app.db.models import Base, UserModel, SettingModel, ChatMessageModel
from app.core.settings import get_settings


def test_aiosqlite_completely_unreferenced():
  """Assert that aiosqlite is not installed and cannot be imported."""
  with pytest.raises(ImportError):
    import aiosqlite  # type: ignore


def test_sqlalchemy_orm_models():
  """Assert that all persistence models inherit from SQLAlchemy DeclarativeBase."""
  assert issubclass(UserModel, Base)
  assert issubclass(SettingModel, Base)
  assert issubclass(ChatMessageModel, Base)
  assert UserModel.__tablename__ == "users"
  assert SettingModel.__tablename__ == "settings"
  assert ChatMessageModel.__tablename__ == "chat_messages"


def test_postgres_url_generation(monkeypatch: pytest.MonkeyPatch):
  """Assert that Settings correctly constructs PostgreSQL URLs for SQLAlchemy."""
  monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/funcAssist")
  get_settings.cache_clear()
  settings = get_settings()
  url = settings.get_database_url(for_sqlalchemy=True)
  assert url is not None
  assert url.startswith("postgresql+psycopg://user:pass@localhost:5432/qa_mgmt")
  get_settings.cache_clear()

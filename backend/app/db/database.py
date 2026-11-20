"""SQLAlchemy Async and Sync PostgreSQL Database Connection and ORM Initialization.
"""

from __future__ import annotations

import inspect
import logging
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncGenerator, Callable, Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import get_settings
from app.db.models import Base

logger = logging.getLogger(__name__)

# Global engine and sessionmaker singletons
_async_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

_sync_engine = None
_sync_session_factory: Optional[sessionmaker[Session]] = None

# Overrides for testing
_async_session_override: Optional[Callable[[], AsyncGenerator[AsyncSession, None]]] = None
_sync_session_override: Optional[Callable[[], Generator[Session, None]]] = None


def set_session_override(override: Optional[Callable[[], AsyncGenerator[AsyncSession, None]]]) -> None:
  """Set an override generator for get_db() during testing."""
  global _async_session_override
  _async_session_override = override


def set_sync_session_override(override: Optional[Callable[[], Generator[Session, None]]]) -> None:
  """Set an override generator for get_sync_db() during testing."""
  global _sync_session_override
  _sync_session_override = override


def get_async_engine() -> AsyncEngine:
  """Get or create singleton async SQLAlchemy engine."""
  global _async_engine, _async_session_factory
  if _async_engine is None:
    url = get_settings().get_database_url(for_sqlalchemy=True)
    if not url:
      url = "postgresql+psycopg://postgres:postgres@localhost:5432/qa_mgmt"
    _async_engine = create_async_engine(
      url,
      echo=False,
      future=True,
      pool_pre_ping=True,
      connect_args={"connect_timeout": 3},
    )
    _async_session_factory = async_sessionmaker(
      bind=_async_engine,
      class_=AsyncSession,
      expire_on_commit=False,
      autoflush=False,
    )
  return _async_engine


def get_sync_engine():
  """Get or create singleton sync SQLAlchemy engine."""
  global _sync_engine, _sync_session_factory
  if _sync_engine is None:
    url = get_settings().get_database_url(for_sqlalchemy=True)
    if not url:
      url = "postgresql+psycopg://postgres:postgres@localhost:5432/funcAssist"
    _sync_engine = create_engine(
      url,
      echo=False,
      future=True,
      pool_pre_ping=True,
      connect_args={"connect_timeout": 3},
    )
    _sync_session_factory = sessionmaker(
      bind=_sync_engine,
      expire_on_commit=False,
      autoflush=False,
    )
  return _sync_engine


async def _commit_async(session: Any) -> None:
  """Commit if the session supports it (test doubles may not)."""
  commit = getattr(session, "commit", None)
  if commit is None:
    return
  res = commit()
  if inspect.isawaitable(res):
    await res


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
  """Provide an asynchronous SQLAlchemy session that commits on success and rolls back on error.

  Callers that already committed (e.g. AsyncUnitOfWork) are unaffected: a commit with no
  pending changes is a no-op. If the final commit fails it is rolled back and re-raised.
  """
  if _async_session_override is not None:
    async with _async_session_override() as session:
      try:
        yield session
        await _commit_async(session)
      except BaseException:
        if hasattr(session, "rollback"):
          res = session.rollback()
          if inspect.isawaitable(res):
            await res
        raise
    return

  get_async_engine()
  assert _async_session_factory is not None
  async with _async_session_factory() as session:
    try:
      yield session
      await session.commit()
    except BaseException:
      # BaseException: a cancelled request (client disconnect) must not leave half-written work.
      await session.rollback()
      raise


@contextmanager
def get_sync_db() -> Generator[Session, None]:
  """Provide a synchronous SQLAlchemy session that commits on success and rolls back on error."""
  if _sync_session_override is not None:
    with _sync_session_override() as session:
      try:
        yield session
        if hasattr(session, "commit"):
          session.commit()
      except BaseException:
        if hasattr(session, "rollback"):
          session.rollback()
        raise
    return

  get_sync_engine()
  assert _sync_session_factory is not None
  with _sync_session_factory() as session:
    try:
      yield session
      session.commit()
    except BaseException:
      session.rollback()
      raise

async def init_db() -> None:
  """Initialize PostgreSQL schema and tables using SQLAlchemy ORM Metadata."""
  try:
    engine = get_async_engine()
    async with engine.begin() as conn:
      await conn.run_sync(Base.metadata.create_all)
    logger.info("PostgreSQL database tables initialized successfully via SQLAlchemy ORM.")
  except Exception as exc:
    logger.warning("Could not automatically initialize PostgreSQL tables: %s", exc)


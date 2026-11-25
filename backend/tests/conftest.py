import pytest
import pytest_asyncio
from fastapi import FastAPI
import app.main as main_module
from app.api.deps import get_current_user, get_current_admin_user
from app.db.database import set_session_override, set_sync_session_override
from tests.fake_session import GLOBAL_FAKE_STORAGE, fake_async_db, fake_sync_db

FAKE_TEST_USER = {
    "id": "test-user-id",
    "username": "Usuario",
    "role": "admin",
    "status": "approved",
    "full_name": None,
}


@pytest.fixture(autouse=True)
def setup_fake_db():
  GLOBAL_FAKE_STORAGE.clear()
  set_session_override(fake_async_db)
  set_sync_session_override(fake_sync_db)
  yield
  GLOBAL_FAKE_STORAGE.clear()
  set_session_override(None)
  set_sync_session_override(None)


@pytest.fixture(autouse=True)
def override_test_auth(request, monkeypatch):
  mod_name = getattr(request.module, "__name__", "").lower()
  if "test_auth_api" in mod_name:
    yield
    return

  orig_fastapi_init = FastAPI.__init__

  def patched_fastapi_init(self, *args, **kwargs):
    orig_fastapi_init(self, *args, **kwargs)
    self.dependency_overrides[get_current_user] = lambda: FAKE_TEST_USER
    self.dependency_overrides[get_current_admin_user] = lambda: FAKE_TEST_USER

  monkeypatch.setattr(FastAPI, "__init__", patched_fastapi_init)
  main_module.app.dependency_overrides[get_current_user] = lambda: FAKE_TEST_USER
  main_module.app.dependency_overrides[get_current_admin_user] = lambda: FAKE_TEST_USER
  yield
  main_module.app.dependency_overrides.pop(get_current_user, None)
  main_module.app.dependency_overrides.pop(get_current_admin_user, None)


@pytest.fixture(autouse=True)
def isolated_security_log(tmp_path, monkeypatch):
  """Security decisions are logged to disk; tests must never write into the real data directory."""
  from app.ai import logging as ai_logging

  monkeypatch.setattr(ai_logging, "SECURITY_DIR", tmp_path / "security-log")
  yield

@pytest.fixture(scope="session")
def pg_engine():
  import os

  from sqlalchemy import create_engine, text

  from app.db.models import Base

  url = os.environ.get("TEST_DATABASE_URL")
  if not url:
    pytest.skip("TEST_DATABASE_URL is not set: start a pgvector PostgreSQL to run the SQL repository tests")
  engine = create_engine(url)
  with engine.begin() as connection:
    # Parallel test processes (mutation testing) must not create the schema at the same time.
    connection.execute(text("SELECT pg_advisory_xact_lock(7284651)"))
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(connection)
  yield engine
  engine.dispose()


@pytest.fixture
def pg_session(pg_engine):
  """A session whose changes are rolled back when the test ends, so every test starts from an empty database."""
  from sqlalchemy.orm import Session

  connection = pg_engine.connect()
  transaction = connection.begin()
  session = Session(bind=connection, join_transaction_mode="create_savepoint")
  yield session
  session.close()
  transaction.rollback()
  connection.close()


@pytest_asyncio.fixture
async def pg_async_session(pg_engine):
  """The same, for repositories that take an AsyncSession."""
  import os

  from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

  engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
  async with engine.connect() as connection:
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    await session.close()
    await transaction.rollback()
  await engine.dispose()


def pytest_asyncio_loop_factories(config, item):
  """psycopg cannot run async on Windows' default event loop; only the tests that use it get a selector loop."""
  import asyncio
  import selectors
  import sys

  if sys.platform == "win32" and "pg_async_session" in getattr(item, "fixturenames", ()):
    return {"selector": lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())}
  return {"default": asyncio.new_event_loop}

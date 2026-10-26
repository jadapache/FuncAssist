import pytest
from app.db.database import set_session_override, set_sync_session_override
from tests.fake_session import GLOBAL_FAKE_STORAGE, fake_async_db, fake_sync_db


@pytest.fixture(autouse=True)
def setup_fake_db():
  GLOBAL_FAKE_STORAGE.clear()
  set_session_override(fake_async_db)
  set_sync_session_override(fake_sync_db)
  yield
  GLOBAL_FAKE_STORAGE.clear()
  set_session_override(None)
  set_sync_session_override(None)

import pytest
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

import pytest
from fastapi import FastAPI
import app.main as main_module
from app.api.deps import get_current_user, get_current_admin_user

FAKE_TEST_USER = {
    "id": "unit-test-user-id",
    "username": "Usuario",
    "role": "admin",
    "status": "approved",
    "full_name": None,
}


@pytest.fixture(autouse=True)
def override_unit_test_user(monkeypatch):
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

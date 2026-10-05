import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.settings import LOCAL_DIR

client = TestClient(app)


@pytest.fixture
def clean_app_json():
    """Clean app.json before and after test."""
    settings_path = LOCAL_DIR / "settings" / "app.json"
    if settings_path.exists():
        settings_path.unlink()
    yield
    if settings_path.exists():
        settings_path.unlink()


def test_get_user_profile_default(clean_app_json):
    """Test getting default user profile."""
    response = client.get("/api/user/profile")
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "Usuario"
    assert data["user_role"] == "admin"


def test_first_time_setup(clean_app_json):
    """Test first-time setup."""
    response = client.post(
        "/api/user/setup",
        json={"display_name": "Test User", "user_role": "funcional"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "Test User"
    assert data["user_role"] == "funcional"

    # Verify it persisted
    response = client.get("/api/user/profile")
    data = response.json()
    assert data["display_name"] == "Test User"
    assert data["user_role"] == "funcional"


def test_update_user_profile(clean_app_json):
    """Test updating user profile."""
    # Setup
    client.post(
        "/api/user/setup",
        json={"display_name": "Original Name", "user_role": "pm"},
    )

    # Update display name only
    response = client.put(
        "/api/user/profile",
        json={"display_name": "Updated Name"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "Updated Name"
    assert data["user_role"] == "pm"

    # Update role only
    response = client.put(
        "/api/user/profile",
        json={"user_role": "funcional"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "Updated Name"
    assert data["user_role"] == "funcional"

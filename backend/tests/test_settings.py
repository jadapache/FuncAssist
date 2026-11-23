import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_current_user():
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "test-user-001",
        "username": "testuser",
        "role": "admin",
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)




def test_update_ai_settings_endpoints():
    # Update with provider and model
    res = client.put(
        "/api/ai/settings",
        json={"provider": "groq", "model": "llama-3.3-70b-versatile"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] == "groq"
    assert data["model"] == "llama-3.3-70b-versatile"

    # Update with inference_provider and inference_model aliases
    res_alias = client.put(
        "/api/ai/settings",
        json={"inference_provider": "builtin", "inference_model": "qwen3.5:2b"},
    )
    assert res_alias.status_code == 400
    assert "WebLLM" in res_alias.json()["detail"]












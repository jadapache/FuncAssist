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


def test_ai_settings_endpoints():
    res = client.get("/api/ai/settings")
    assert res.status_code == 200
    data = res.json()
    assert "provider" in data
    assert "active_api_key_set" in data


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


def test_ai_models_catalog_endpoint():
    res = client.get("/api/ai/models/catalog")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, dict)


def test_ai_templates_endpoints():
    res = client.get("/api/ai/prompts")
    assert res.status_code == 200
    data = res.json()
    assert "prompts" in data

    res_rubrics = client.get("/api/ai/rubrics")
    assert res_rubrics.status_code == 200
    data_rubrics = res_rubrics.json()
    assert "rubrics" in data_rubrics

    # Check filtering by tag
    res_tagged = client.get("/api/ai/prompts?tag=transcript_summary")
    assert res_tagged.status_code == 200
    tagged_data = res_tagged.json()
    assert len(tagged_data.get("prompts", [])) >= 6

    # Check transcription summary templates endpoint
    res_sum_tmpls = client.get("/api/transcription/summary-templates")
    assert res_sum_tmpls.status_code == 200
    sum_data = res_sum_tmpls.json()
    assert "templates" in sum_data
    assert len(sum_data["templates"]) >= 6


def test_templates_router():
    res = client.get("/api/templates")
    assert res.status_code == 200
    data = res.json()
    assert "templates" in data


def test_pm_and_qa_features_validation():
    # Calling qa with unknown feature should return 404
    res = client.post(
        "/api/features/qa/invalid_feature",
        json={"query": "test", "sources": ["knowledge"], "document_ids": []},
    )
    assert res.status_code == 404

    # Calling change-impact without sources or documents should return 400
    res = client.post(
        "/api/features/change-impact",
        json={"query": "test", "sources": [], "document_ids": []},
    )
    assert res.status_code == 400


def test_openapi_schema_generation():
    res = client.get("/openapi.json")
    assert res.status_code == 200
    schema = res.json()
    assert "openapi" in schema
    assert "paths" in schema
    assert "/api/ai/prompts/{feature}" in schema["paths"]
    assert "/api/templates/{template_id}" in schema["paths"]


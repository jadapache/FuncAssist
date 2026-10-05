import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ai_settings_endpoints():
    res = client.get("/api/ai/settings")
    assert res.status_code == 200
    data = res.json()
    assert "provider" in data
    assert "active_api_key_set" in data


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

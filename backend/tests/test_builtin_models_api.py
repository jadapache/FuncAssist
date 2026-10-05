import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_list_builtin_models():
    response = client.get("/api/ai/builtin/models")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "models" in data
    assert len(data["models"]) >= 5
    ids = [m["id"] for m in data["models"]]
    assert "qwen2.5:1.5b" in ids
    assert "qwen2.5:3b" in ids
    assert "llama3.2:1b" in ids


def test_download_unknown_builtin_model():
    response = client.post("/api/ai/builtin/download/unknown_nonexistent_model")
    assert response.status_code == 500


def test_delete_non_downloaded_builtin_model():
    response = client.delete("/api/ai/builtin/qwen2.5:1.5b")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True

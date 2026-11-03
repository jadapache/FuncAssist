import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_builtin_model_endpoints_are_not_exposed():
    response = client.get("/api/ai/builtin/models")
    assert response.status_code == 404


def test_download_unknown_builtin_model():
    response = client.post("/api/ai/builtin/download/unknown_nonexistent_model")
    assert response.status_code >= 400


def test_delete_non_downloaded_builtin_model():
    response = client.delete("/api/ai/builtin/qwen2.5:1.5b")
    assert response.status_code >= 400


def test_get_builtin_download_tasks():
    response = client.get("/api/ai/builtin/tasks")
    assert response.status_code == 404


def test_cancel_builtin_model_download():
    response = client.post("/api/ai/builtin/cancel/qwen2.5:1.5b")
    assert response.status_code >= 400



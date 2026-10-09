"""Unit tests for Frontier Models Catalog Sync Service and API endpoints."""

from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.ai.frontier_sync import (
    fetch_litellm_cost_map,
    sync_frontier_models_catalog,
    get_frontier_sync_status,
)


@pytest.mark.asyncio
async def test_fetch_litellm_cost_map_offline_fallback():
    """Verify that when remote HTTP fails, bundled LiteLLM cost map is used without throwing."""
    with patch("httpx.AsyncClient.get", side_effect=Exception("Connection refused")):
        cost_map, source = await fetch_litellm_cost_map(timeout_seconds=0.1)
        assert source == "bundled_litellm"
        assert isinstance(cost_map, dict)
        assert len(cost_map) > 0


@pytest.mark.asyncio
async def test_sync_frontier_models_catalog_execution(tmp_path):
    """Verify sync_frontier_models_catalog updates and writes valid models with pricing and context."""
    test_catalog_path = tmp_path / "models_catalog.json"

    with patch("app.ai.frontier_sync.CATALOG_FILE", test_catalog_path):
        result = await sync_frontier_models_catalog(force_remote=False)
        assert result["status"] == "success"
        assert result["models_count"] >= 15
        assert test_catalog_path.exists()

        status = get_frontier_sync_status()
        assert status["status"] == "success"
        assert status["models_count"] == result["models_count"]


def test_sync_api_endpoints():
    """Verify POST /api/ai/models/sync and GET /api/ai/models/sync-status."""
    client = TestClient(app)

    # Test sync status
    res_status = client.get("/api/ai/models/sync-status")
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert "status" in data_status

    # Test trigger sync
    res_sync = client.post("/api/ai/models/sync?force_remote=false")
    assert res_sync.status_code == 200
    data_sync = res_sync.json()
    assert "sync" in data_sync
    assert "catalog" in data_sync
    assert data_sync["sync"]["status"] == "success"
    assert len(data_sync["catalog"]["models"]) > 0

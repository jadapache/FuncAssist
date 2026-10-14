"""Tests for Model Context Protocol (MCP) Server and Client APIs."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.db.database as db_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    test_db_path = tmp_path / "test_mcp_app.db"
    monkeypatch.setattr(db_module, "get_db_path", lambda: test_db_path)
    import asyncio
    asyncio.run(db_module.init_db())
    yield test_db_path


def test_mcp_server_info():
    """Verify public MCP info and config snippets for Claude / Cursor."""
    resp = client.get("/api/mcp/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "online"
    assert data["name"] == "funcassist-mcp-server"
    assert data["toolsCount"] >= 5
    assert "directUrl" in data
    assert "sseUrl" in data
    assert "configSnippets" in data
    assert "claudeDesktop" in data["configSnippets"]
    assert "cursor" in data["configSnippets"]


def test_mcp_jsonrpc_lifecycle():
    """Verify standard MCP 2024-11-05 JSON-RPC methods."""
    # 1. initialize
    init_resp = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-agent", "version": "1.0"},
            },
        },
    )
    assert init_resp.status_code == 200
    init_data = init_resp.json()
    assert init_data["id"] == 1
    assert init_data["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in init_data["result"]["capabilities"]

    # 2. tools/list
    tools_resp = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
        },
    )
    assert tools_resp.status_code == 200
    tools_data = tools_resp.json()
    tools = tools_data["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "funcassist_search_knowledge" in tool_names
    assert "funcassist_list_templates" in tool_names
    assert "funcassist_plan_document_operations" in tool_names
    assert "funcassist_create_qa_test_plan" in tool_names
    assert "funcassist_summarize_standup" in tool_names

    # 3. tools/call -> funcassist_create_qa_test_plan
    call_resp = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "funcassist_create_qa_test_plan",
                "arguments": {
                    "feature_name": "Autenticación Biométrica",
                    "description": "Inicio de sesión seguro con huella digital o FaceID",
                    "test_type": "regression",
                },
            },
        },
    )
    assert call_resp.status_code == 200
    call_data = call_resp.json()
    content = call_data["result"]["content"]
    assert len(content) > 0
    assert "Autenticación Biométrica" in content[0]["text"]
    assert "TC-01" in content[0]["text"]

    # 4. tools/call -> funcassist_summarize_standup
    standup_resp = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "funcassist_summarize_standup",
                "arguments": {
                    "yesterday": "Desarrollé la integración MCP",
                    "today": "Conectar paneles en el Frontend",
                    "blockers": "Ninguno",
                    "project": "QA Core",
                },
            },
        },
    )
    assert standup_resp.status_code == 200
    standup_text = standup_resp.json()["result"]["content"][0]["text"]
    assert "Daily Standup" in standup_text
    assert "QA Core" in standup_text

    # 5. resources/list
    res_resp = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/list",
        },
    )
    assert res_resp.status_code == 200
    assert len(res_resp.json()["result"]["resources"]) >= 2


def test_mcp_servers_crud():
    """Verify external MCP server management (CRUD)."""
    # 1. Create external server
    create_resp = client.post(
        "/api/mcp/servers",
        json={
            "name": "GitHub Tool Server",
            "transport": "sse",
            "url": "https://mcp.example.com/github/sse",
            "headers": {"Authorization": "Bearer gh_token_123"},
            "enabled": True,
        },
    )
    assert create_resp.status_code == 200
    server_data = create_resp.json()
    server_id = server_data["id"]
    assert server_data["name"] == "GitHub Tool Server"
    assert server_data["headers"]["Authorization"] == "Bearer gh_token_123"

    # 2. List servers
    list_resp = client.get("/api/mcp/servers")
    assert list_resp.status_code == 200
    servers = list_resp.json()
    assert len(servers) == 1
    assert servers[0]["id"] == server_id

    # 3. Update server
    update_resp = client.put(
        f"/api/mcp/servers/{server_id}",
        json={"name": "GitHub Enterprise Tool Server", "enabled": False},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "GitHub Enterprise Tool Server"
    assert update_resp.json()["enabled"] is False

    # 4. Delete server
    del_resp = client.delete(f"/api/mcp/servers/{server_id}")
    assert del_resp.status_code == 200

    # 5. Confirm deletion
    list_after = client.get("/api/mcp/servers")
    assert list_after.status_code == 200
    assert len(list_after.json()) == 0

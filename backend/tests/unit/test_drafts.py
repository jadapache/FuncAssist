import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app
from app.core.settings import USER_DRAFTS_DIR, GENERATED_INDEX_FILE, USER_DOCUMENTS_DIR
from app.features.drafts.storage import (
  delete_generated_draft,
  get_generated_draft,
  list_generated_drafts,
  normalize_specification,
  save_draft_session,
)


@pytest.fixture
def client():
  return TestClient(app)


def test_specification_normalization():
  assert normalize_specification("levantamiento") == "Levantamiento"
  assert normalize_specification("inventario_requerimientos") == "Inventario"
  assert normalize_specification("mejoras") == "Mejoras"
  assert normalize_specification("analisis_qa") == "Mejoras"
  assert normalize_specification("unknown") == "Levantamiento"


def test_draft_session_persistence_and_index():
  session_id = "test-session-12345"
  session_data = {
    "id": session_id,
    "name": "Levantamiento Sistema Core",
    "specification": "Levantamiento",
    "lastInteraction": "2026-10-07T14:00:00Z",
    "messages": [
      {"role": "user", "content": "Genera el levantamiento", "timestamp": "14:00"},
      {"role": "assistant", "content": "Aquí está el levantamiento.", "timestamp": "14:01"},
    ],
    "documentContent": "# Levantamiento Sistema Core\n\nDetalles del sistema.",
    "artifacts": [
      {
        "id": "art-1",
        "title": "Documento Levantamiento",
        "extension": "docx",
        "content": "# Documento Levantamiento\n\nEspecificación funcional.",
        "createdAt": "14:01",
      }
    ],
  }

  saved = save_draft_session(session_data)
  assert saved["id"] == session_id
  assert saved["specification"] == "Levantamiento"
  assert saved["artifact_count"] == 1

  # Check filesystem in Documents/QA MGMT/Borradores/Levantamiento/
  folder_path = Path(saved["folder_path"])
  assert folder_path.exists()
  assert (folder_path / "chat.json").exists()
  assert (folder_path / "chat.md").exists()
  assert (folder_path / "Documento_Levantamiento.md").exists()
  assert (folder_path / "metadata.json").exists()

  # Check index in Generated/_index.json
  assert GENERATED_INDEX_FILE.exists()
  drafts = list_generated_drafts(specification="Levantamiento")
  assert any(d["id"] == session_id for d in drafts)

  # Fetch detail
  detail = get_generated_draft(session_id)
  assert detail is not None
  assert detail["title"] == "Levantamiento Sistema Core"

  # Delete
  deleted = delete_generated_draft(session_id)
  assert deleted is True
  assert not folder_path.exists()
  assert not any(d["id"] == session_id for d in list_generated_drafts())


def test_drafts_api_endpoints(client: TestClient):
  # 1. Save via API
  res = client.post(
    "/api/drafts/save",
    json={
      "id": "api-draft-session-999",
      "name": "Inventario Modulo Ventas",
      "specification": "Inventario",
      "messages": [{"role": "user", "content": "Hola", "timestamp": "10:00"}],
      "documentContent": "# Inventario Ventas",
      "artifacts": [
        {"id": "a-1", "title": "Inventario_Tabla", "extension": "xlsx", "content": "# Tabla\n| ID | Nombre |\n|---|---|\n| 1 | Test |"}
      ]
    },
  )
  assert res.status_code == 200
  data = res.json()
  assert data["ok"] is True
  assert data["draft"]["specification"] == "Inventario"

  # 2. List
  list_res = client.get("/api/drafts/list?specification=Inventario")
  assert list_res.status_code == 200
  items = list_res.json()["drafts"]
  assert any(d["id"] == "api-draft-session-999" for d in items)

  # 3. Get Detail
  get_res = client.get("/api/drafts/api-draft-session-999")
  assert get_res.status_code == 200
  assert get_res.json()["draft"]["title"] == "Inventario Modulo Ventas"

  # 4. Delete
  del_res = client.delete("/api/drafts/api-draft-session-999")
  assert del_res.status_code == 200

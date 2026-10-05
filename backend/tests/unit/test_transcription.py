from __future__ import annotations

import io
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.features.transcription.storage import (
  get_file_hash,
  validate_file,
  save_media_file,
  save_transcription_record,
  get_transcription_record,
  update_transcription_summary,
  rename_transcription_speakers,
  delete_transcription_record,
  cleanup_old_files,
)
from app.features.transcription.diarization import SpeakerDiarization
from app.features.transcription.summarizer import parse_summary_markdown_or_json
from app.features.inventario.docx_builder import create_inventario_docx
from app.features.levantamiento.docx_builder import create_levantamiento_docx


@pytest.fixture
def client():
  return TestClient(app)


def test_file_validation():
  # Valid audio and video
  ok, err = validate_file("meeting.mp3", 1024)
  assert ok is True
  assert err is None

  ok, err = validate_file("demo.mp4", 5 * 1024 * 1024)
  assert ok is True
  assert err is None

  ok, err = validate_file("recording.wav", 100)
  assert ok is True

  ok, err = validate_file("audio.m4a", 100)
  assert ok is True

  # Invalid format
  ok, err = validate_file("document.pdf", 100)
  assert ok is False
  assert "no soportado" in err

  # Exceeding size
  ok, err = validate_file("huge.mp4", 3 * 1024 * 1024 * 1024)
  assert ok is False
  assert "2GB" in err


def test_file_hash():
  data1 = b"test audio byte content"
  data2 = b"test audio byte content"
  data3 = b"different content"
  assert get_file_hash(data1) == get_file_hash(data2)
  assert get_file_hash(data1) != get_file_hash(data3)


def test_media_storage_and_record():
  dummy_bytes = b"RIFF....WAVEfmt ...."
  entry = save_media_file(
    file_bytes=dummy_bytes,
    filename="test_meeting.wav",
    title="Reunion de Kickoff",
    description="Notas iniciales",
  )
  assert entry["id"] is not None
  assert entry["title"] == "Reunion de Kickoff"
  assert entry["size_bytes"] == len(dummy_bytes)

  # Create transcription record
  record_id = "test-trans-123"
  record = {
    "id": record_id,
    "media_id": entry["id"],
    "metadata": {"title": "Reunion de Kickoff"},
    "language": "es",
    "duration_seconds": 60.0,
    "created_at": "2026-10-01T10:00:00Z",
    "segments": [
      {"start": 0.0, "end": 4.5, "speaker": "Participante 1", "text": "Buenos días a todos."},
      {"start": 5.0, "end": 10.0, "speaker": "Participante 2", "text": "Hola, revisemos los requisitos de autenticación."},
    ],
    "summary": {
      "participants": ["Participante 1", "Participante 2"],
      "topics": ["Autenticación"],
      "decisions": ["Usar OAuth 2.0"],
      "requirements": ["Soporte SSO"],
      "action_items": ["Definir matriz de permisos"],
    },
  }
  saved = save_transcription_record(record)
  assert saved["id"] == record_id

  fetched = get_transcription_record(record_id)
  assert fetched is not None
  assert len(fetched["segments"]) == 2

  # Rename speakers
  renamed = rename_transcription_speakers(
    record_id,
    {"Participante 1": "Carlos Facilitador", "Participante 2": "Elena Arquitecta"},
  )
  assert renamed is not None
  assert renamed["segments"][0]["speaker"] == "Carlos Facilitador"
  assert "Elena Arquitecta" in renamed["summary"]["participants"]

  # Update summary
  new_summary = {
    "participants": ["Carlos Facilitador", "Elena Arquitecta"],
    "topics": ["Autenticación SSO y Roles"],
    "decisions": ["Usar OAuth 2.0 y JWT"],
    "requirements": ["REQ-01 SSO con Azure AD"],
    "action_items": ["Documentar endpoints"],
  }
  updated = update_transcription_summary(record_id, new_summary)
  assert updated["summary"]["decisions"] == ["Usar OAuth 2.0 y JWT"]

  # Cleanup record
  deleted = delete_transcription_record(record_id)
  assert deleted is True
  assert get_transcription_record(record_id) is None


def test_diarization_heuristics():
  diarizer = SpeakerDiarization()
  segments = [
    {"start": 0.0, "end": 3.0, "text": "Primera intervención", "speaker": "Speaker 1"},
    {"start": 5.0, "end": 8.0, "text": "Segunda intervención con pausa", "speaker": "Speaker 1"},
    {"start": 8.2, "end": 11.0, "text": "Mismo hablante continuo", "speaker": "Speaker 1"},
  ]
  labeled = diarizer.diarize_segments(segments)
  assert len(labeled) == 3
  # The gap between 3.0 and 5.0 is 2.0s > 1.2s, so speaker alternates
  assert labeled[0]["speaker"] != labeled[1]["speaker"]


def test_summary_markdown_parsing():
  sample_md = """
  ### Participantes
  - Ana Gómez (Líder QA)
  - Juan Pérez (Product Owner)

  ### Temas Discutidos
  - Flujo de creación de historias de usuario
  - Integración con Jira y GitHub

  ### Decisiones Tomadas
  - Implementar validación en dos pasos

  ### Requerimientos Mencionados
  - RF-01: Generar exportables en Word (.docx)

  ### Compromisos y Próximos Pasos
  - Enviar especificación final el viernes
  """
  summary = parse_summary_markdown_or_json(sample_md)
  assert len(summary.participants) == 2
  assert "Ana Gómez (Líder QA)" in summary.participants
  assert "Flujo de creación de historias de usuario" in summary.topics
  assert "Implementar validación en dos pasos" in summary.decisions
  assert "RF-01: Generar exportables en Word (.docx)" in summary.requirements
  assert "Enviar especificación final el viernes" in summary.action_items


def test_inventario_and_levantamiento_docx_builders():
  md_inventario = """
  # Inventario de Requerimientos
  ## 1. Información General
  - **Proyecto:** QA MGMT
  - **Fecha:** 2026-10-01
  ## 2. Requerimientos Iniciales
  | ID | Requerimiento | Prioridad |
  |---|---|---|
  | INV-01 | Módulo de Transcripciones | Alta |
  """
  inv_bytes = create_inventario_docx(md_inventario, title="Inventario de Requerimientos")
  assert isinstance(inv_bytes, bytes)
  assert len(inv_bytes) > 1000

  md_levantamiento = """
  # Levantamiento Detallado
  ## 1. Requerimientos Funcionales
  ### RF-001: Transcripción Automática
  - **Prioridad:** Alta
  - **Criterios de Aceptación:**
    - [ ] Soporte de archivos de hasta 2GB
    - [x] Extracción de resumen con IA
  """
  lev_bytes = create_levantamiento_docx(md_levantamiento, title="Levantamiento Detallado")
  assert isinstance(lev_bytes, bytes)
  assert len(lev_bytes) > 1000


def test_transcription_api_lifecycle(client: TestClient):
  # 1. Upload
  audio_content = b"ID3\x03\x00\x00\x00\x00\x00#TSSE\x00\x00\x00\x0f\x00\x00\x03Lavf58.29.100\x00"
  upload_res = client.post(
    "/api/transcription/upload",
    files={"file": ("meeting_demo.mp3", io.BytesIO(audio_content), "audio/mpeg")},
    data={"title": "Reunión de Levantamiento QA", "description": "Transcripción de prueba"},
  )
  assert upload_res.status_code == 200
  data = upload_res.json()
  assert data["ok"] is True
  media_id = data["media_id"]
  assert media_id is not None

  # 2. Trigger transcription
  trans_res = client.post(
    f"/api/transcription/transcribe/{media_id}",
    json={"mode": "auto", "enable_diarization": True},
  )
  assert trans_res.status_code == 200
  trans_data = trans_res.json()
  transcription_id = trans_data["transcription_id"]

  # 3. Check status
  status_res = client.get(f"/api/transcription/status/{transcription_id}")
  assert status_res.status_code in (200, 404)

  # 4. Save manual record to verify result and export endpoints
  save_transcription_record({
    "id": transcription_id,
    "media_id": media_id,
    "metadata": {"title": "Reunión de Levantamiento QA", "description": "Transcripción de prueba"},
    "language": "es",
    "duration_seconds": 120.0,
    "created_at": "2026-10-01T10:00:00Z",
    "segments": [
      {"start": 0.0, "end": 10.0, "speaker": "Participante 1", "text": "Bienvenidos al levantamiento."},
    ],
    "summary": {
      "participants": ["Participante 1"],
      "topics": ["Levantamiento"],
      "decisions": ["Aprobado"],
      "requirements": ["REQ-1"],
      "action_items": ["Continuar"],
    },
  })

  res_get = client.get(f"/api/transcription/result/{transcription_id}")
  assert res_get.status_code == 200
  res_data = res_get.json()
  assert res_data["metadata"]["title"] == "Reunión de Levantamiento QA"

  # 5. Edit summary
  summary_edit_res = client.put(
    f"/api/transcription/summary/{transcription_id}",
    json={
      "summary": {
        "participants": ["Dr. Gomez", "Ing. Perez"],
        "topics": ["Arquitectura"],
        "decisions": ["Microservicios"],
        "requirements": ["REQ-02"],
        "action_items": ["Diagramar"],
      }
    },
  )
  assert summary_edit_res.status_code == 200

  # 6. Save to knowledge base
  kb_res = client.post(
    f"/api/transcription/save-to-knowledge/{transcription_id}",
    json={"custom_tags": ["sprint_1", "kickoff"]},
  )
  assert kb_res.status_code == 200
  assert kb_res.json()["ok"] is True

  # 7. List all
  list_res = client.get("/api/transcription/list")
  assert list_res.status_code == 200
  assert any(t["id"] == transcription_id for t in list_res.json()["transcriptions"])

  # 8. Export Inventario XLSX and Levantamiento DOCX
  inv_exp = client.post(
    "/api/transcription/export/inventario",
    json={"content": "# Inventario\n- Item 1", "title": "Inventario_Test"},
  )
  assert inv_exp.status_code == 200
  assert inv_exp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

  lev_exp = client.post(
    "/api/transcription/export/levantamiento",
    json={"content": "# Levantamiento\n- Item 2", "title": "Levantamiento_Test"},
  )
  assert lev_exp.status_code == 200
  assert lev_exp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

  # 9. Delete
  del_res = client.delete(f"/api/transcription/{transcription_id}")
  assert del_res.status_code == 200


def test_transcription_cancel_and_models(client: TestClient):
  # Available models
  models_res = client.get("/api/transcription/available-models")
  assert models_res.status_code == 200
  data = models_res.json()
  assert "active_model_label" in data
  assert "available_providers" in data

  # Cancel transcription
  cancel_res = client.post("/api/transcription/cancel/test-fake-id-123")
  assert cancel_res.status_code == 200
  assert cancel_res.json()["ok"] is True


def test_upload_stream_and_sse_events(client: TestClient):
  from app.api.transcription_stream import get_or_create_progress_queue

  audio_content = b"ID3\x03\x00\x00\x00\x00\x00#TSSE\x00\x00\x00\x0f\x00\x00\x03Lavf58.29.100\x00" * 50
  upload_res = client.post(
    "/api/transcription/upload-stream",
    files={"file": ("stream_demo.mp3", io.BytesIO(audio_content), "audio/mpeg")},
    data={"title": "Reunión en Tiempo Real", "description": "Prueba de streaming SSE"},
  )
  assert upload_res.status_code == 200
  data = upload_res.json()
  assert data["ok"] is True
  assert "transcription_id" in data
  assert "media_id" in data

  transcription_id = data["transcription_id"]
  queue = get_or_create_progress_queue(transcription_id)
  assert queue is not None


def test_progress_stream_endpoint(client: TestClient):
  from app.api.transcription_stream import _LATEST_PROGRESS
  _LATEST_PROGRESS["test-stream-id"] = {"stage": "complete", "progress": 100, "message": "done"}
  with client.stream("GET", "/api/transcription/progress-stream/test-stream-id") as response:
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    lines = []
    for line in response.iter_lines():
      if line:
        lines.append(line)
      if len(lines) >= 1:
        break
    assert any("data:" in l for l in lines)


def test_local_whisper_models_endpoint(client: TestClient):
  res = client.get("/api/ai/whisper/models")
  assert res.status_code == 200
  data = res.json()
  assert data["ok"] is True
  assert "models" in data
  assert len(data["models"]) >= 5
  assert any(m["id"] == "tiny" for m in data["models"])
  assert any(m["id"] == "base" for m in data["models"])




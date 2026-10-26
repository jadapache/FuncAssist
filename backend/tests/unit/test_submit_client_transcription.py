import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_submit_client_transcription_endpoint():
  payload = {
    "id": "test_client_transcription_123",
    "title": "Reunión de Prueba Client-Side",
    "description": "Prueba de ingesta desde navegador",
    "language": "es",
    "duration_seconds": 120.5,
    "text": "Hola a todos, esta es una transcripción de prueba procesada en el navegador.",
    "segments": [
      {
        "start": 0.0,
        "end": 4.5,
        "speaker": "Participante 1",
        "text": "Hola a todos,",
      },
      {
        "start": 4.5,
        "end": 10.0,
        "speaker": "Participante 1",
        "text": "esta es una transcripción de prueba procesada en el navegador.",
      },
    ],
    "generate_summary_now": False,
  }

  response = client.post("/api/transcription/submit-client-transcription", json=payload)
  assert response.status_code == 200
  data = response.json()
  assert data["ok"] is True
  assert data["transcription"]["id"] == "test_client_transcription_123"
  assert data["transcription"]["metadata"]["title"] == "Reunión de Prueba Client-Side"
  assert len(data["transcription"]["segments"]) == 2
  assert data["transcription"]["text"].startswith("Hola a todos")

  # Clean up test record
  client.delete("/api/transcription/test_client_transcription_123")

import pytest
from unittest.mock import patch
from app.ai.catalog import get_model_catalog

@pytest.mark.asyncio
async def test_catalog_retrieval_and_task_types():
  res = await get_model_catalog(refresh=False)
  assert len(res.models) > 0
  assert res.source in {"local_json", "models.dev (en vivo)", "local_cache", "database_or_frontier", "ai_models_catalog_db"}

  chat_models = [m for m in res.models if m.task_type == "chat_writing"]
  voice_models = [m for m in res.models if m.task_type == "transcription"]

  assert len(chat_models) > 0
  assert len(voice_models) > 0

  for m in chat_models:
    assert m.task_label == "Redacción y Chat"
    assert "whisper" not in m.id.lower()
    assert not m.id.lower().endswith(".gguf")
    assert m.provider not in {"builtin", "local"}

  for m in voice_models:
    assert m.task_label in {"Transcripción y Voz", "Transcripción de Audio"}
    assert "whisper" in f"{m.id} {m.raw_id} {m.name}".lower()
    assert m.provider in {"groq", "openai", "browser_asr"}


@pytest.mark.asyncio
async def test_catalog_filter_by_task_type():
  chat_catalog = await get_model_catalog(task_type="chat_writing")
  assert all(m.task_type == "chat_writing" for m in chat_catalog.models)
  assert all("whisper" not in m.id.lower() for m in chat_catalog.models)

  voice_catalog = await get_model_catalog(task_type="transcription")
  assert len(voice_catalog.models) >= 2
  assert all(m.task_type == "transcription" for m in voice_catalog.models)
  assert all(m.provider in {"groq", "openai", "browser_asr"} for m in voice_catalog.models)


@pytest.mark.asyncio
async def test_catalog_offline_error_handling():
  with patch("app.ai.catalog.load_local_catalog", return_value=[]):
    res = await get_model_catalog(refresh=True)
    assert res.error == "Error de conexión, no se pudo obtener los modelos"
    assert len(res.models) == 0


@pytest.mark.asyncio
async def test_catalog_no_image_models_in_chat_writing():
  chat_catalog = await get_model_catalog(task_type="chat_writing")
  for m in chat_catalog.models:
    text = f"{m.id} {m.name} {m.description}".lower()
    assert "banana" not in text
    assert "imagen" not in text
    assert "dall-e" not in text

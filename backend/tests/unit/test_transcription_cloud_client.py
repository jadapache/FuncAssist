from __future__ import annotations

import json

import httpx
import pytest

from app.features.transcription import whisper_cloud
from app.features.transcription.errors import TranscriptionJobError
from app.features.transcription.whisper_cloud import SpeechClient, SpeechTarget, resolve_diarization_target, resolve_speech_target


@pytest.fixture
def settings(monkeypatch):
  values: dict = {}
  monkeypatch.setattr(whisper_cloud, "get_ai_settings", lambda user_id=None: values)
  monkeypatch.delenv("GROQ_API_KEY", raising=False)
  monkeypatch.delenv("OPENAI_API_KEY", raising=False)
  return values


class TestTargets:
  def test_configured_openai_wins_over_groq(self, settings):
    settings.update(transcription_provider="openai", groq_api_key="g", openai_api_key="o")
    target = resolve_speech_target("u1")
    assert target.provider == "openai" and target.model == "whisper-1"

  def test_falls_back_to_available_key(self, settings):
    settings.update(transcription_provider="openai", groq_api_key="g")
    assert resolve_speech_target("u1").provider == "groq"

  def test_text_only_model_is_replaced(self, settings):
    settings.update(transcription_provider="openai", openai_api_key="o", transcription_model="gpt-4o-transcribe")
    assert resolve_speech_target("u1").model == "whisper-1"

  def test_no_keys(self, settings):
    with pytest.raises(TranscriptionJobError) as exc:
      resolve_speech_target("u1")
    assert exc.value.code == "no_credentials"

  def test_diarization_needs_openai_and_setting(self, settings):
    settings.update(groq_api_key="g")
    assert resolve_diarization_target("u1", True) is None
    settings.update(openai_api_key="o")
    assert resolve_diarization_target("u1", True).diarize is True
    assert resolve_diarization_target("u1", False) is None
    settings.update(transcription_diarization="off")
    assert resolve_diarization_target("u1", True) is None


def _client(handler, monkeypatch, provider="groq", diarize=False):
  monkeypatch.setattr(whisper_cloud.config, "num_retries", lambda: 2)
  client = SpeechClient(SpeechTarget(provider=provider, api_key="k", model="m", diarize=diarize))
  client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
  return client


@pytest.fixture
def audio(tmp_path):
  path = tmp_path / "chunk_000.mp3"
  path.write_bytes(b"ID3fake")
  return path


class TestSpeechClient:
  @pytest.mark.asyncio
  async def test_retries_rate_limit_then_succeeds(self, monkeypatch, audio):
    calls = {"n": 0}

    def handler(request):
      calls["n"] += 1
      if calls["n"] == 1:
        return httpx.Response(429, headers={"retry-after": "0.01"}, json={"error": {"message": "slow down"}})
      return httpx.Response(200, json={
        "language": "es",
        "segments": [{"start": 0.0, "end": 2.0, "text": " Hola ", "no_speech_prob": 0.1, "avg_logprob": -0.2, "compression_ratio": 1.1}],
      })

    client = _client(handler, monkeypatch)
    result = await client.transcribe(audio, language="es", prompt="Glosario")
    await client.aclose()
    assert calls["n"] == 2 and client.retries == 1
    assert result["segments"][0]["text_raw"] == "Hola"
    assert result["segments"][0]["_metrics"]["no_speech_prob"] == 0.1

  @pytest.mark.asyncio
  async def test_auth_error_is_not_retried(self, monkeypatch, audio):
    calls = {"n": 0}

    def handler(request):
      calls["n"] += 1
      return httpx.Response(401, json={"error": {"message": "Invalid API Key"}})

    client = _client(handler, monkeypatch)
    with pytest.raises(TranscriptionJobError) as exc:
      await client.transcribe(audio, language="es")
    await client.aclose()
    assert exc.value.code == "auth_error" and calls["n"] == 1

  @pytest.mark.asyncio
  async def test_diarized_response(self, monkeypatch, audio):
    seen: dict = {}

    def handler(request):
      seen["body"] = request.content
      return httpx.Response(200, content=json.dumps({
        "segments": [
          {"start": 0.0, "end": 1.0, "text": "Hola", "speaker": "A"},
          {"start": 1.0, "end": 2.0, "text": "Buenas", "speaker": "B"},
        ],
      }))

    ref = audio.parent / "ref_S1.mp3"
    ref.write_bytes(b"ID3ref")
    client = _client(handler, monkeypatch, provider="openai", diarize=True)
    result = await client.diarize(audio, language="es", known_speakers=[("S1", ref)])
    await client.aclose()
    assert [s["speaker_label"] for s in result["segments"]] == ["A", "B"]
    assert b"diarized_json" in seen["body"] and b"known_speaker_names[]" in seen["body"]

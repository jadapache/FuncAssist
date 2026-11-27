"""Cloud speech clients: target resolution, error detail, retries with backoff and the response shapes."""

import logging

import httpx
import pytest

from app.features.transcription import whisper_cloud as wc
from app.features.transcription.errors import TranscriptionJobError

# --- targets ----------------------------------------------------------------------


@pytest.fixture
def settings(monkeypatch):
  cfg = {}
  monkeypatch.setattr(wc, "get_ai_settings", lambda user_id=None: cfg)
  for name in ("GROQ_API_KEY", "OPENAI_API_KEY"):
    monkeypatch.delenv(name, raising=False)
  monkeypatch.setattr(wc, "pick_transcription_model", lambda provider, configured: configured or None)
  return cfg


def test_target_label_and_cost():
  assert wc.SpeechTarget("groq", "k", "m").label == "Groq Whisper (m)"
  assert wc.SpeechTarget("openai", "k", "m", diarize=True).label == "OpenAI diarización (m)"
  assert wc.SpeechTarget("groq", "k", "m").estimate_cost(120) == 0.0037
  assert wc.SpeechTarget("openai", "k", "m", diarize=True).estimate_cost(60) == 0.006
  assert wc.SpeechTarget("other", "k", "m").estimate_cost(60) == 0.006


def test_keys_prefer_the_transcription_key_then_the_general_key_then_the_environment(settings, monkeypatch):
  monkeypatch.setenv("GROQ_API_KEY", "env-g")
  monkeypatch.setenv("OPENAI_API_KEY", "env-o")
  assert wc._keys(settings) == {"groq": "env-g", "openai": "env-o"}
  settings.update(groq_api_key="g", openai_api_key="o")
  assert wc._keys(settings) == {"groq": "g", "openai": "o"}
  settings.update(transcription_groq_api_key="tg", transcription_openai_api_key="to")
  assert wc._keys(settings) == {"groq": "tg", "openai": "to"}


def test_available_providers_reports_which_keys_exist(settings):
  settings["groq_api_key"] = "g"
  assert wc.available_providers("u") == {"groq": True, "openai": False}


def test_automatic_provider_prefers_groq_and_explicit_openai_prefers_openai(settings):
  settings.update(groq_api_key="g", openai_api_key="o")
  assert wc.resolve_speech_target("u").provider == "groq"
  settings["transcription_provider"] = "OpenAI"
  assert wc.resolve_speech_target("u").provider == "openai"


def test_missing_key_of_the_configured_provider_falls_back_with_a_warning(settings, caplog):
  settings.update(openai_api_key="o", transcription_provider="groq")
  with caplog.at_level(logging.WARNING):
    target = wc.resolve_speech_target("u")
  assert target.provider == "openai" and target.api_key == "o"
  assert any("groq has no API key; using openai" in r.getMessage() for r in caplog.records)


def test_automatic_provider_with_one_key_does_not_warn(settings, caplog):
  settings["openai_api_key"] = "o"
  with caplog.at_level(logging.WARNING):
    assert wc.resolve_speech_target("u").provider == "openai"
  assert caplog.records == []


def test_without_any_key_there_are_no_credentials(settings):
  with pytest.raises(TranscriptionJobError) as raised:
    wc.resolve_speech_target("u")
  assert raised.value.code == "no_credentials"


def test_the_catalog_model_wins_and_a_replaced_model_is_logged(settings, monkeypatch, caplog):
  settings.update(groq_api_key="g", transcription_model="  my-model ")
  monkeypatch.setattr(wc, "pick_transcription_model", lambda provider, configured: "catalog-model")
  with caplog.at_level(logging.INFO):
    target = wc.resolve_speech_target("u")
  assert target.model == "catalog-model"
  assert any("'my-model' is not a groq catalog model" in r.getMessage() and "using catalog-model" in r.getMessage() for r in caplog.records)


def test_a_configured_model_the_catalog_confirms_is_not_reported(settings, caplog):
  settings.update(groq_api_key="g", transcription_model="whisper-x")
  with caplog.at_level(logging.INFO):
    assert wc.resolve_speech_target("u").model == "whisper-x"
  assert caplog.records == []


def test_the_fixed_model_is_the_last_resort(settings, monkeypatch):
  settings.update(groq_api_key="g", openai_api_key="o")
  monkeypatch.setattr(wc, "pick_transcription_model", lambda provider, configured: None)
  assert wc.resolve_speech_target("u").model == "whisper-large-v3"
  settings["transcription_provider"] = "openai"
  assert wc.resolve_speech_target("u").model == "whisper-1"


@pytest.fixture
def diarization(settings, monkeypatch):
  settings["openai_api_key"] = "o"
  monkeypatch.setenv("TRANSCRIPTION_DIARIZE_MODEL", "diar-1")
  state = {"result": ("diar-1", True)}
  monkeypatch.setattr(wc, "pick_diarization_model", lambda provider, configured: state["result"])
  return state


def test_diarization_is_only_resolved_when_requested_enabled_and_keyed(diarization, settings):
  assert wc.resolve_diarization_target("u", False) is None
  settings["transcription_diarization"] = "OFF"
  assert wc.resolve_diarization_target("u", True) is None
  settings["transcription_diarization"] = "on"
  target = wc.resolve_diarization_target("u", True)
  assert (target.provider, target.api_key, target.model, target.diarize) == ("openai", "o", "diar-1", True)
  settings["openai_api_key"] = ""
  assert wc.resolve_diarization_target("u", True) is None


def test_diarization_trusts_the_configured_model_when_the_catalog_is_unknown(diarization):
  diarization["result"] = (None, False)
  assert wc.resolve_diarization_target("u", True).model == "diar-1"


def test_diarization_is_skipped_with_a_warning_when_the_catalog_has_no_model(diarization, caplog):
  diarization["result"] = (None, True)
  with caplog.at_level(logging.WARNING):
    assert wc.resolve_diarization_target("u", True) is None
  assert any("No OpenAI diarization model in the catalog (configured 'diar-1')" in r.getMessage() for r in caplog.records)


def test_a_substituted_diarization_model_is_logged(diarization, caplog):
  diarization["result"] = ("diar-2", True)
  with caplog.at_level(logging.INFO):
    assert wc.resolve_diarization_target("u", True).model == "diar-2"
  assert any("'diar-1' is not in the catalog; using diar-2" in r.getMessage() for r in caplog.records)


def test_a_confirmed_diarization_model_is_not_reported(diarization, caplog):
  with caplog.at_level(logging.INFO):
    wc.resolve_diarization_target("u", True)
  assert caplog.records == []


# --- error detail and retry-after ---------------------------------------------------


def _response(status=400, **kw):
  return httpx.Response(status, **kw)


@pytest.mark.parametrize("response, expected", [
  (_response(json={"error": {"message": "bad key"}}), "bad key"),
  (_response(json={"error": {"code": 1}}), '{"error":{"code":1}}'),
  (_response(json={"error": "plain"}), "plain"),
  (_response(json={"error": None}), '{"error":null}'),
  (_response(json=["a"]), '["a"]'),
  (_response(text="not json " + "x" * 600), ("not json " + "x" * 600)[:500]),
])
def test_error_detail_reads_the_provider_message_or_the_raw_body(response, expected):
  assert wc._error_detail(response) == expected


@pytest.mark.parametrize("headers, expected", [
  ({"retry-after": "7"}, 7.0), ({"retry-after": "1.5"}, 1.5), ({"retry-after": "soon"}, None), ({}, None), ({"retry-after": ""}, None),
])
def test_retry_after_is_a_number_of_seconds_or_nothing(headers, expected):
  assert wc._retry_after(_response(headers=headers)) == expected


# --- requests, retries and backoff --------------------------------------------------


class _Wire:
  """Scripted HTTP replies; the client under test sends its requests through it."""

  def __init__(self, replies):
    self.replies, self.requests = list(replies), []

  def __call__(self, request):
    self.requests.append(request)
    reply = self.replies.pop(0)
    if isinstance(reply, Exception):
      raise reply
    return reply


@pytest.fixture
def client_for(monkeypatch, tmp_path):
  sleeps = []

  async def fake_sleep(seconds):
    sleeps.append(seconds)

  monkeypatch.setattr(wc.asyncio, "sleep", fake_sleep)
  monkeypatch.setattr(wc.random, "uniform", lambda a, b: 0.5)
  monkeypatch.setenv("TRANSCRIPTION_NUM_RETRIES", "3")

  def build(replies, provider="groq"):
    wire = _Wire(replies)
    client = wc.SpeechClient(wc.SpeechTarget(provider, "secret", "model-1"))
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(wire))
    client.wire, client.sleeps = wire, sleeps
    return client

  build.audio = tmp_path / "a.mp3"
  build.audio.write_bytes(b"audio")
  return build


def _ok(**body):
  return httpx.Response(200, json=body)


@pytest.mark.asyncio
async def test_a_successful_post_sends_the_key_the_form_and_the_file(client_for):
  client = client_for([_ok(text="hi")])
  async with client:
    assert await client._post(client_for.audio, {"model": "model-1"}) == {"text": "hi"}
  request = client.wire.requests[0]
  assert str(request.url) == wc.ENDPOINTS["groq"] and request.headers["authorization"] == "Bearer secret"
  assert b'filename="a.mp3"' in request.content and b"audio/mpeg" in request.content and b'name="model"' in request.content


@pytest.mark.asyncio
async def test_other_extensions_are_sent_as_binary_and_openai_uses_its_endpoint(client_for, tmp_path):
  wav = tmp_path / "a.wav"
  wav.write_bytes(b"w")
  client = client_for([_ok()], provider="openai")
  await client._post(wav, {})
  assert str(client.wire.requests[0].url) == wc.ENDPOINTS["openai"]
  assert b"application/octet-stream" in client.wire.requests[0].content


@pytest.mark.asyncio
async def test_a_permanent_error_is_raised_at_once_without_retrying(client_for):
  client = client_for([httpx.Response(401, json={"error": {"message": "bad key"}})])
  with pytest.raises(TranscriptionJobError) as raised:
    await client._post(client_for.audio, {})
  assert raised.value.code == "auth_error" and raised.value.detail == "bad key"
  assert len(client.wire.requests) == 1 and client.retries == 0 and client.sleeps == []


@pytest.mark.asyncio
async def test_transient_errors_are_retried_with_exponential_backoff(client_for, caplog):
  client = client_for([httpx.Response(500, text="down"), httpx.Response(503, text="down"), _ok(text="ok")])
  with caplog.at_level(logging.WARNING):
    assert await client._post(client_for.audio, {}) == {"text": "ok"}
  assert client.retries == 2 and client.sleeps == [2 * 1 + 0.5, 2 * 2 + 0.5]
  assert any("Transient groq error" in r.getMessage() and "retry 1/3 in 2.5s" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_retry_after_overrides_the_backoff_and_is_capped_at_a_minute(client_for):
  client = client_for([httpx.Response(429, headers={"retry-after": "7"}), httpx.Response(429, headers={"retry-after": "500"}), _ok()])
  await client._post(client_for.audio, {})
  assert client.sleeps == [7.0, 60.0]


@pytest.mark.asyncio
async def test_network_errors_are_retried_too(client_for):
  client = client_for([httpx.ConnectTimeout("slow"), _ok(text="ok")])
  assert await client._post(client_for.audio, {}) == {"text": "ok"}
  assert client.retries == 1


@pytest.mark.asyncio
async def test_the_last_transient_error_is_raised_once_the_attempts_run_out(client_for, monkeypatch):
  monkeypatch.setenv("TRANSCRIPTION_NUM_RETRIES", "1")
  client = client_for([httpx.Response(500, text="a"), httpx.Response(500, text="b")])
  with pytest.raises(TranscriptionJobError) as raised:
    await client._post(client_for.audio, {})
  assert raised.value.code == "provider_unavailable" and raised.value.detail == "b"
  assert len(client.wire.requests) == 2 and client.retries == 1


@pytest.mark.asyncio
async def test_without_retries_the_first_failure_is_final(client_for, monkeypatch):
  monkeypatch.setenv("TRANSCRIPTION_NUM_RETRIES", "0")
  client = client_for([httpx.Response(500, text="a")])
  with pytest.raises(TranscriptionJobError):
    await client._post(client_for.audio, {})
  assert client.retries == 0


# --- responses ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcribe_requests_verbose_json_and_keeps_segments_with_text(client_for):
  body = {"language": "es", "text": "uno dos", "segments": [
    {"start": 1, "end": 2.5, "text": " uno ", "no_speech_prob": 0.1, "avg_logprob": -0.2, "compression_ratio": 1.1},
    {"start": 3, "end": 4, "text": "   "},
    {"text": "dos"},
  ]}
  client = client_for([_ok(**body)])
  result = await client.transcribe(client_for.audio, language="es", prompt="glosario")
  assert result["language"] == "es" and result["text"] == "uno dos"
  assert result["segments"] == [
    {"start": 1.0, "end": 2.5, "text_raw": "uno", "_metrics": {"no_speech_prob": 0.1, "avg_logprob": -0.2, "compression_ratio": 1.1}},
    {"start": 0.0, "end": 0.0, "text_raw": "dos", "_metrics": {"no_speech_prob": None, "avg_logprob": None, "compression_ratio": None}},
  ]
  content = client.wire.requests[0].content
  for expected in (b"verbose_json", b'name="temperature"', b'name="language"', b"glosario", b"model-1"):
    assert expected in content


@pytest.mark.asyncio
async def test_transcribe_omits_language_and_prompt_when_empty(client_for):
  client = client_for([_ok(text="")])
  result = await client.transcribe(client_for.audio, language=None)
  content = client.wire.requests[0].content
  assert b'name="language"' not in content and b'name="prompt"' not in content
  assert result == {"language": None, "segments": [], "text": ""}


@pytest.mark.asyncio
async def test_transcribe_falls_back_to_the_plain_text_as_one_segment(client_for):
  client = client_for([_ok(text=" todo junto ", duration=12.5, language="en")])
  result = await client.transcribe(client_for.audio, language="es")
  assert result["language"] == "en"
  assert result["segments"] == [{"start": 0.0, "end": 12.5, "text_raw": "todo junto", "_metrics": {}}]
  client = client_for([_ok(text="x")])
  assert (await client.transcribe(client_for.audio, language="es"))["segments"][0]["end"] == 0.0


@pytest.mark.asyncio
async def test_diarize_labels_the_speakers_and_sends_known_speaker_clips(client_for, tmp_path):
  clip = tmp_path / "clip.wav"
  clip.write_bytes(b"clip")
  body = {"language": "es", "text": "hola", "segments": [
    {"start": 0, "end": 1, "text": "hola", "speaker": "B"},
    {"start": 1, "end": 2, "text": " ", "speaker": "A"},
    {"start": 2, "end": 3, "text": "chao"},
  ]}
  client = client_for([_ok(**body)], provider="openai")
  result = await client.diarize(client_for.audio, language="es", known_speakers=[("Ana", clip)])
  assert result["segments"] == [
    {"start": 0.0, "end": 1.0, "text_raw": "hola", "speaker_label": "B", "_metrics": {}},
    {"start": 2.0, "end": 3.0, "text_raw": "chao", "speaker_label": "A", "_metrics": {}},
  ]
  content = client.wire.requests[0].content
  for expected in (b"diarized_json", b'name="chunking_strategy"', b"known_speaker_names[]", b"Ana", b"data:audio/wav;base64,Y2xpcA=="):
    assert expected in content


@pytest.mark.asyncio
async def test_diarize_without_known_speakers_or_language_sends_neither(client_for):
  client = client_for([_ok(text="")], provider="openai")
  result = await client.diarize(client_for.audio, language=None)
  content = client.wire.requests[0].content
  assert b"known_speaker" not in content and b'name="language"' not in content
  assert result == {"language": None, "segments": [], "text": ""}


def test_known_speaker_clips_keep_their_mime_type(tmp_path):
  mp3 = tmp_path / "c.mp3"
  mp3.write_bytes(b"x")
  assert wc._data_url(mp3).startswith("data:audio/mpeg;base64,")


@pytest.mark.asyncio
async def test_short_audio_is_one_request_joined_into_text(settings, client_for, monkeypatch):
  settings["groq_api_key"] = "g"
  built = []

  class Fake(wc.SpeechClient):
    def __init__(self, target):
      super().__init__(target)
      self._client = httpx.AsyncClient(transport=httpx.MockTransport(_Wire([_ok(segments=[{"text": "uno"}, {"text": "dos"}])])))
      built.append(target)

  monkeypatch.setattr(wc, "SpeechClient", Fake)
  assert await wc.transcribe_short_audio(client_for.audio, "u") == "uno dos"
  assert built[0].provider == "groq"


@pytest.mark.asyncio
async def test_short_audio_falls_back_to_the_plain_text(settings, client_for, monkeypatch):
  settings["groq_api_key"] = "g"

  class Fake(wc.SpeechClient):
    def __init__(self, target):
      super().__init__(target)
      self._client = httpx.AsyncClient(transport=httpx.MockTransport(_Wire([_ok(text=" suelto ", segments=[])])))

  monkeypatch.setattr(wc, "SpeechClient", Fake)
  assert await wc.transcribe_short_audio(client_for.audio, "u") == "suelto"

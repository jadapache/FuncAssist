"""Pipeline tests: preprocessing branches, plan reuse, diarization, LLM cleanup and error paths."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.features.transcription import config, media, metrics, pipeline, progress, records, storage
from app.features.transcription.errors import TranscriptionJobError
from app.features.transcription.pipeline import JobOptions, TranscriptionPipeline, _first_error, _StageTicker
from app.features.transcription.progress import ProgressReporter
from app.features.transcription.whisper_cloud import SpeechTarget

OWNER_ID = "test-user-id"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
  monkeypatch.setattr(storage, "TRANSCRIPTIONS_DIR", tmp_path / "transcriptions")
  monkeypatch.setattr(metrics, "LOG_DIR", tmp_path / "logs")
  progress._LATEST.clear()
  progress._SUBSCRIBERS.clear()
  yield tmp_path
  progress._LATEST.clear()
  progress._SUBSCRIBERS.clear()


class FakeSpeechClient:
  calls: list[str] = []
  fail_on: dict[str, BaseException] = {}
  block: asyncio.Event | None = None
  diarize_calls: list[Any] = []

  def __init__(self, target: SpeechTarget) -> None:
    self.target = target
    self.retries = 1

  async def __aenter__(self):
    return self

  async def __aexit__(self, *exc):
    return None

  async def transcribe(self, path, *, language=None, prompt=""):
    FakeSpeechClient.calls.append(path.stem)
    if FakeSpeechClient.block is not None:
      await FakeSpeechClient.block.wait()
    error = FakeSpeechClient.fail_on.pop(path.stem, None)
    if error:
      raise error
    return {
      "language": "es",
      "segments": [
        {"start": 0.5, "end": 3.0, "text_raw": "Eh, bueno, revisemos el inventario.", "_metrics": {}},
        {"start": 3.0, "end": 5.0, "text_raw": "Subtítulos realizados por la comunidad de Amara.org", "_metrics": {}},
      ],
    }

  async def diarize(self, path, *, language=None, known_speakers=()):
    FakeSpeechClient.calls.append(path.stem)
    FakeSpeechClient.diarize_calls.append(list(known_speakers))
    labels = [k for k, _ in known_speakers] or ["A", "B"]
    labels = (labels + labels)[:2]
    return {
      "language": "es",
      "segments": [
        {"start": 0.0, "end": 4.0, "text_raw": "Hola a todos, empecemos.", "speaker_label": labels[0], "_metrics": {}},
        {"start": 4.0, "end": 9.0, "text_raw": "Perfecto, yo reviso el presupuesto.", "speaker_label": labels[1], "_metrics": {}},
      ],
    }


def install_fakes(monkeypatch, *, diarize: bool = False) -> dict[str, Any]:
  FakeSpeechClient.calls = []
  FakeSpeechClient.fail_on = {}
  FakeSpeechClient.block = None
  FakeSpeechClient.diarize_calls = []
  state: dict[str, Any] = {"duration": 150.0, "silences": [(100.0, 110.0)], "settings": {}, "clip_fail": False}

  async def probe(path):
    return state["duration"]

  async def extract(source, dest, duration, on_progress=None):
    if on_progress:
      on_progress(0.5)
    dest.write_bytes(b"RIFF")
    return dest

  async def noise(wav):
    return -60.0

  async def silences(wav, threshold, min_silence, duration):
    return state["silences"]

  async def export(wav, regions, dest):
    dest.write_bytes(b"ID3")
    return dest

  async def clip(wav, start, end, dest):
    if state["clip_fail"]:
      raise RuntimeError("clip failed")
    dest.write_bytes(b"ID3")
    return dest

  monkeypatch.setattr(media, "probe_duration", probe)
  monkeypatch.setattr(media, "extract_audio", extract)
  monkeypatch.setattr(media, "measure_noise_floor", noise)
  monkeypatch.setattr(media, "detect_silences", silences)
  monkeypatch.setattr(media, "export_regions", export)
  monkeypatch.setattr(media, "export_clip", clip)
  monkeypatch.setattr(pipeline, "SpeechClient", FakeSpeechClient)
  monkeypatch.setattr(pipeline, "resolve_speech_target", lambda user_id: SpeechTarget("groq", "k", "whisper-large-v3"))
  diar = SpeechTarget("openai", "k", "gpt-4o-transcribe-diarize", diarize=True)
  monkeypatch.setattr(pipeline, "resolve_diarization_target", lambda user_id, requested: diar if diarize and requested else None)
  monkeypatch.setattr(pipeline, "_user_settings", lambda user_id: state["settings"])
  return state


async def create_uploaded_record(tid: str, *, with_media: bool = True) -> None:
  folder = storage.get_transcription_dir(tid)
  folder.mkdir(parents=True, exist_ok=True)
  path = folder / "media.mp3"
  if with_media:
    path.write_bytes(b"ID3media")
  entry = {
    "id": tid, "transcription_id": tid, "original_filename": "reunion.mp3", "filename": "reunion.mp3",
    "stored_filename": "media.mp3", "path": str(path), "size_bytes": 8, "file_size_formatted": "8 B",
    "hash": "", "is_video": False, "title": "Reunión", "description": "", "created_at": "2026-11-21T00:00:00+00:00",
  }
  await records.save_record(storage.initial_record(entry, OWNER_ID))


def make_pipeline(tid: str, **options: Any) -> TranscriptionPipeline:
  reporter = ProgressReporter(tid, media_id=tid, title="Reunión", model_info="Whisper")
  return TranscriptionPipeline(tid, OWNER_ID, JobOptions(summarize=False, **options), reporter)


class TestJobOptions:
  def test_from_dict_ignores_unknown_keys(self):
    opts = JobOptions.from_dict({"language": "en", "bogus": 1, "diarize": False})
    assert opts.language == "en" and opts.diarize is False
    assert JobOptions.from_dict(None) == JobOptions()
    assert opts.to_dict()["language"] == "en"


class TestHelpers:
  def test_first_error_prefers_typed_then_non_cancel(self):
    typed = TranscriptionJobError("rate_limit")
    group = BaseExceptionGroup("g", [asyncio.CancelledError(), BaseExceptionGroup("inner", [typed])])
    assert _first_error(group) is typed
    boom = ValueError("x")
    assert _first_error(BaseExceptionGroup("g", [asyncio.CancelledError(), boom])) is boom
    only_cancel = asyncio.CancelledError()
    assert _first_error(BaseExceptionGroup("g", [only_cancel])) is only_cancel

  def test_user_settings_swallows_errors(self, monkeypatch):
    import app.ai.providers.factory as factory

    def boom(user_id=None):
      raise RuntimeError("db down")

    monkeypatch.setattr(factory, "get_ai_settings", boom)
    assert pipeline._user_settings("u") == {}
    monkeypatch.setattr(factory, "get_ai_settings", lambda user_id=None: {"a": 1})
    assert pipeline._user_settings("u") == {"a": 1}


  @pytest.mark.asyncio
  async def test_stage_ticker_throttles_and_skips_other_stage(self):
    reporter = ProgressReporter("tick", media_id="tick", title="t", model_info="m")
    await reporter.update("preprocessing", 0.0)
    ticker = _StageTicker(reporter, "preprocessing", "msg", (0.0, 0.5))
    ticker(1.0)
    ticker(1.0)  # throttled
    assert len(ticker._tasks) == 1
    await asyncio.gather(*list(ticker._tasks))
    assert reporter.snapshot["stage_progress"] == 0.5
    await reporter.update("transcribing", 0.0)
    await ticker._tick(0.9)
    assert reporter.snapshot["stage"] == "transcribing"

  def test_prompt_for_uses_vocabulary_and_previous_tail(self, monkeypatch):
    install_fakes(monkeypatch)
    p = make_pipeline("prompt-0001", vocabulary="Glosario")
    chunk = type("C", (), {"index": 1})()
    prev = {"segments": [{"text_raw": "eh vamos a revisar el plan"}]}
    prompt = p._prompt_for(chunk, {0: prev})
    assert prompt.startswith("Glosario. ")
    assert "revisar el plan" in prompt
    assert p._prompt_for(type("C", (), {"index": 0})(), {}) == "Glosario"

  def test_llm_cleanup_provider_branches(self, monkeypatch):
    import app.ai.providers.factory as factory

    state = install_fakes(monkeypatch)
    p = make_pipeline("llmprov-0001")
    p.settings = {"provider": "ollama"}
    assert p._llm_cleanup_provider() is None
    p.settings = {}

    def boom(**kw):
      raise RuntimeError("no provider")

    monkeypatch.setattr(factory, "resolve_provider", boom)
    assert p._llm_cleanup_provider() is None
    local = type("P", (), {"id": "webllm"})()
    monkeypatch.setattr(factory, "resolve_provider", lambda **kw: local)
    assert p._llm_cleanup_provider() is None
    cloud = type("P", (), {"id": "openai"})()
    monkeypatch.setattr(factory, "resolve_provider", lambda **kw: cloud)
    assert p._llm_cleanup_provider() is cloud


class TestRun:
  @pytest.mark.asyncio
  async def test_missing_record_and_missing_media(self, monkeypatch):
    install_fakes(monkeypatch)
    with pytest.raises(TranscriptionJobError) as exc:
      await make_pipeline("nope-0001").run()
    assert exc.value.code == "corrupt_media"
    await create_uploaded_record("nomedia-0001", with_media=False)
    with pytest.raises(TranscriptionJobError) as exc:
      await make_pipeline("nomedia-0001").run()
    assert "ya no existe" in exc.value.user_message

  @pytest.mark.asyncio
  async def test_too_long_recording(self, monkeypatch):
    state = install_fakes(monkeypatch)
    state["duration"] = 10_000.0
    monkeypatch.setattr(config, "max_duration_s", lambda: 3600.0)
    await create_uploaded_record("long-0001")
    with pytest.raises(TranscriptionJobError) as exc:
      await make_pipeline("long-0001").run()
    assert exc.value.code == "too_long"
    assert "2.8 h" in exc.value.user_message


  @pytest.mark.asyncio
  async def test_no_trim_and_plan_reuse(self, monkeypatch):
    install_fakes(monkeypatch)
    monkeypatch.setattr(config, "trim_silence_enabled", lambda: False)
    await create_uploaded_record("plan-0001")
    p = make_pipeline("plan-0001")
    result = await p.run()
    assert result.record["status"] == "complete"
    assert result.record["silence_trimmed_s"] == 0.0
    plan_file = p.folder / "plan.json"
    plan = json.loads(plan_file.read_text())
    assert plan["regions"] == [[0.0, 150.0]] and plan["provider"] == "groq"
    assert result.metrics["retries"] == 1
    assert result.metrics["cost_estimate"] == pytest.approx(150 / 60 * 0.00185, abs=1e-5)
    # Second run starts from audio.wav (no extraction) and reuses the stored plan.
    p2 = make_pipeline("plan-0001")
    assert p2._load_plan(plan_file) is None  # target not yet resolved -> provider mismatch
    p2.target = SpeechTarget("groq", "k", "m")
    assert p2._load_plan(plan_file) == plan
    plan_file.write_text("{not json")
    assert p2._load_plan(plan_file) is None

  @pytest.mark.asyncio
  async def test_corrupt_chunk_result_is_ignored(self, monkeypatch):
    install_fakes(monkeypatch)
    p = make_pipeline("chunkres-0001")
    chunk = type("C", (), {"index": 0})()
    p.chunk_dir.mkdir(parents=True)
    assert p._load_result(chunk) is None
    p._result_path(chunk).write_text("garbage")
    assert p._load_result(chunk) is None



  @pytest.mark.asyncio
  async def test_llm_cleanup_used_and_fallback(self, monkeypatch):
    install_fakes(monkeypatch)
    calls = []

    class Provider:
      id = "openai"

      async def complete(self, messages, max_tokens=0):
        calls.append(messages)
        items = json.loads(messages[1].content)
        return type("R", (), {"text": json.dumps([{"id": i["id"], "text": "Revisemos el inventario."} for i in items])})()

    p_holder: dict[str, Any] = {"p": Provider()}
    monkeypatch.setattr(TranscriptionPipeline, "_llm_cleanup_provider", lambda self: p_holder["p"])
    await create_uploaded_record("llm-0001")
    p = make_pipeline("llm-0001", cleanup="llm")
    result = await p.run()
    assert calls and result.record["cleanup"]["mode"] == "llm"
    assert result.record["cleanup"]["llm_segments"] >= 1

    p_holder["p"] = None
    await create_uploaded_record("llm-0002")
    p2 = make_pipeline("llm-0002", cleanup="llm")
    await p2.run()
    assert p2.metrics["cleanup_fallback"] == "rules"

  @pytest.mark.asyncio
  async def test_diarized_job_sends_reference_clips(self, monkeypatch):
    state = install_fakes(monkeypatch, diarize=True)
    state["silences"] = []
    monkeypatch.setattr(config, "chunk_seconds", lambda: 60.0)
    await create_uploaded_record("diar-0001")
    p = make_pipeline("diar-0001")
    result = await p.run()
    rec = result.record
    assert rec["diarization"] == "openai"
    assert set(rec["speakers"]) == {"S1", "S2"}
    assert FakeSpeechClient.calls[0] == "chunk_000"
    # Later chunks get the first chunk's speakers as known references.
    assert FakeSpeechClient.diarize_calls[0] == []
    assert [label for label, _ in FakeSpeechClient.diarize_calls[1]] == ["S1", "S2"]
    assert p.reporter.snapshot["stage"] in {"saving", "diarizing"}

  @pytest.mark.asyncio
  async def test_reference_clip_failure_is_tolerated(self, monkeypatch):
    state = install_fakes(monkeypatch, diarize=True)
    state["silences"] = []
    state["clip_fail"] = True
    monkeypatch.setattr(config, "chunk_seconds", lambda: 60.0)
    await create_uploaded_record("diar-0002")
    result = await make_pipeline("diar-0002").run()
    assert result.record["status"] == "complete"
    assert all(k == [] for k in FakeSpeechClient.diarize_calls)

  @pytest.mark.asyncio
  async def test_chunk_failure_raises_typed_error(self, monkeypatch):
    install_fakes(monkeypatch)
    FakeSpeechClient.fail_on["chunk_000"] = TranscriptionJobError("timeout")
    await create_uploaded_record("fail-0001")
    with pytest.raises(TranscriptionJobError) as exc:
      await make_pipeline("fail-0001").run()
    assert exc.value.code == "timeout"

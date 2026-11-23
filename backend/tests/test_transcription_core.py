"""Unit tests for the pure transcription helpers: errors, config, diarization, metrics, progress."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.exceptions import AudioAnalysisError, FFmpegError
from app.features.transcription import config, diarization, errors, metrics, progress
from app.features.transcription.errors import TranscriptionJobError


# --- errors ------------------------------------------------------------------------------------


class TestErrors:
  def test_unknown_code_falls_back_to_internal(self):
    err = TranscriptionJobError("nope")
    assert err.code == "internal" and err.retryable is True
    assert "internal" in str(err)

  def test_overrides(self):
    err = TranscriptionJobError("rate_limit", "msg", detail="d", retryable=False, retry_after=3.0)
    assert (err.user_message, err.detail, err.retryable, err.retry_after) == ("msg", "d", False, 3.0)
    assert str(err) == "rate_limit: d"

  @pytest.mark.parametrize(
    "status,detail,code",
    [
      (500, "x", "provider_unavailable"),
      (503, "x", "provider_unavailable"),
      (401, "x", "auth_error"),
      (403, "x", "auth_error"),
      (413, "x", "file_too_large"),
      (415, "x", "unsupported_format"),
      (429, "x", "rate_limit"),
      (400, "bad things", "bad_request"),
      (400, "Invalid API Key provided", "auth_error"),
      (418, "teapot", "bad_request"),
    ],
  )
  def test_error_from_status(self, status, detail, code):
    err = errors.error_from_status(status, detail, retry_after=1.5)
    assert err.code == code and err.retry_after == 1.5 and err.detail == detail

  def test_classify_exception(self):
    original = TranscriptionJobError("timeout")
    assert errors.classify_exception(original) is original
    assert errors.classify_exception(asyncio.CancelledError()).code == "cancelled"
    assert errors.classify_exception(httpx.ReadTimeout("t")).code == "timeout"
    assert errors.classify_exception(TimeoutError("t")).code == "timeout"
    assert errors.classify_exception(httpx.ConnectError("c")).code == "provider_unavailable"
    assert errors.classify_exception(httpx.RemoteProtocolError("r")).code == "provider_unavailable"
    ff = errors.classify_exception(FFmpegError("boom", returncode=2))
    assert ff.code == "corrupt_media" and "boom" in ff.detail
    aa = errors.classify_exception(AudioAnalysisError("bad", filename="a.mp3"))
    assert aa.code == "corrupt_media" and "a.mp3" in aa.detail
    fnf = errors.classify_exception(FileNotFoundError("gone"))
    assert fnf.code == "corrupt_media" and "ya no existe" in fnf.user_message
    other = errors.classify_exception(ValueError("x"))
    assert other.code == "internal" and other.detail == "ValueError: x"



# --- config ------------------------------------------------------------------------------------

_ENV = [
  "TRANSCRIPTION_MAX_UPLOAD_MB", "TRANSCRIPTION_MAX_DURATION_S", "TRANSCRIPTION_CHUNK_S",
  "TRANSCRIPTION_CHUNK_CONCURRENCY", "TRANSCRIPTION_MAX_CONCURRENT_JOBS", "TRANSCRIPTION_NUM_RETRIES",
  "TRANSCRIPTION_TIMEOUT_S", "TRANSCRIPTION_HALLUCINATION_FILTER", "TRANSCRIPTION_TRIM_SILENCE",
  "TRANSCRIPTION_MIN_SILENCE_S", "TRANSCRIPTION_TURN_GAP_S", "TRANSCRIPTION_CLEANUP",
  "TRANSCRIPTION_DIARIZE_MODEL", "TRANSCRIPTION_DESKTOP_MODE", "TRANSCRIPTION_LOCAL_ROOTS",
  "TRANSCRIPTION_MEDIA_TTL_DAYS",
]


class TestConfig:
  @pytest.fixture(autouse=True)
  def clean_env(self, monkeypatch):
    for name in _ENV:
      monkeypatch.delenv(name, raising=False)

  def test_defaults(self):
    assert config.max_upload_bytes() == 2048 * 1024 * 1024
    assert config.max_duration_s() == 14_400
    assert config.chunk_seconds() == 600
    assert config.chunk_concurrency("groq") == 2
    assert config.chunk_concurrency("openai") == 4
    assert config.max_concurrent_jobs() == 2
    assert config.num_retries() == 3
    assert config.request_timeout_s() == 300
    assert config.hallucination_filter_enabled() is True
    assert config.trim_silence_enabled() is True
    assert config.min_silence_s() == 2.0
    assert config.turn_gap_s() == 8.0
    assert config.default_cleanup_mode() == "rules"
    assert config.diarize_model() == "gpt-4o-transcribe-diarize"
    assert config.desktop_mode() is False
    assert config.local_roots() == []
    assert config.media_ttl_days() is None


  def test_invalid_values_use_defaults(self, monkeypatch):
    monkeypatch.setenv("TRANSCRIPTION_MAX_DURATION_S", "abc")
    monkeypatch.setenv("TRANSCRIPTION_NUM_RETRIES", "x")
    monkeypatch.setenv("TRANSCRIPTION_CLEANUP", "weird")
    assert config.max_duration_s() == 14_400
    assert config.num_retries() == 3
    assert config.default_cleanup_mode() == "rules"


# --- diarization -------------------------------------------------------------------------------


class TestDiarization:
  def test_mapper_assigns_stable_ids_per_chunk(self):
    mapper = diarization.SpeakerLabelMapper()
    assert mapper.map(0, "A") == "S1"
    assert mapper.map(0, "B") == "S2"
    assert mapper.map(0, "A") == "S1"
    # Same provider label in another chunk is a different speaker unless it is a known id.
    assert mapper.map(1, "A") == "S3"
    assert mapper.map(1, "S2") == "S2"

  def test_mapper_skips_ids_already_known(self):
    mapper = diarization.SpeakerLabelMapper()
    mapper.known.add("S1")
    assert mapper.map(0, "X") == "S2"

  def test_label_segments_default_label(self):
    mapper = diarization.SpeakerLabelMapper()
    out = mapper.label_segments(0, [{"text": "a"}, {"text": "b", "speaker_label": "B"}])
    assert [s["speaker_id"] for s in out] == ["S1", "S2"]
    assert all("speaker_label" not in s for s in out)

  def test_reference_candidates(self):
    segs = [
      {"speaker_id": "S1", "start": 0, "end": 1},  # too short
      {"speaker_id": "S1", "start": 1, "end": 4},
      {"speaker_id": "S2", "start": 4, "end": 20},  # clamped to 8 s
      {"speaker_id": "S1", "start": 20, "end": 25},  # longer -> replaces
      {"start": 0, "end": 10},  # no speaker
      {"speaker_id": "S3", "start": 30, "end": 33},
    ]
    assert diarization.reference_candidates(segs) == [("S1", 20.0, 25.0), ("S2", 4.0, 12.0), ("S3", 30.0, 33.0)]
    assert diarization.reference_candidates(segs, max_speakers=1) == [("S1", 20.0, 25.0)]

  def test_build_speaker_map(self):
    segs = [{"speaker_id": "S2"}, {}, {"speaker_id": "S2"}]
    out = diarization.build_speaker_map(segs, existing={"S2": {"name": "Ana"}})
    assert out == {"S2": {"name": "Ana", "color_index": 0}, "S1": {"name": "Participante 2", "color_index": 1}}
    assert diarization.build_speaker_map([]) == {"S1": {"name": "Participante 1", "color_index": 0}}


# --- metrics -----------------------------------------------------------------------------------


class TestMetrics:
  @pytest.fixture(autouse=True)
  def log_dir(self, tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "LOG_DIR", tmp_path / "logs")
    return tmp_path / "logs"

  def test_read_entries_without_dir(self):
    assert metrics.read_entries() == []

  @pytest.mark.asyncio
  async def test_log_job_computes_rtf_and_reads_back(self, log_dir):
    await metrics.log_job({"provider": "groq", "audio_s": 100, "stage_ms": {"a": 20000, "b": 30000}})
    await metrics.log_job({"provider": "openai", "audio_s": 0, "stage_ms": {}})
    entries = metrics.read_entries()
    assert len(entries) == 2
    assert entries[0]["provider"] == "openai" and "rtf" not in entries[0]
    assert entries[1]["rtf"] == 0.5

  @pytest.mark.asyncio
  async def test_log_job_swallows_os_error(self, monkeypatch):
    def boom(path, line):
      raise OSError("disk full")

    monkeypatch.setattr(metrics, "_append", boom)
    await metrics.log_job({"audio_s": 1})  # no exception

  def test_read_entries_skips_bad_lines_and_limits(self, log_dir):
    log_dir.mkdir(parents=True)
    (log_dir / "2026-01-01.jsonl").write_text('{"n": 1}\n\nnot json\n{"n": 2}\n', encoding="utf-8")
    (log_dir / "2026-01-02.jsonl").write_text('{"n": 3}\n', encoding="utf-8")
    assert [e["n"] for e in metrics.read_entries()] == [3, 2, 1]
    assert [e["n"] for e in metrics.read_entries(limit=2)] == [3, 2]

  def test_read_entries_unreadable_file(self, log_dir, monkeypatch):
    log_dir.mkdir(parents=True)
    (log_dir / "2026-01-01.jsonl").write_text('{"n": 1}\n', encoding="utf-8")
    from pathlib import Path

    def bad_read(self, *a, **k):
      raise OSError("locked")

    monkeypatch.setattr(Path, "read_text", bad_read)
    assert metrics.read_entries() == []

  def test_percentile(self):
    assert metrics._percentile([], 50) is None
    assert metrics._percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5
    assert metrics._percentile([5.0], 95) == 5.0

  def test_summarize(self):
    entries = [
      {"provider": "groq", "status": "complete", "rtf": 0.1, "audio_s": 3600, "silence_trimmed_s": 360,
       "retries": 1, "fillers_removed": 3, "hallucinations_removed": 1, "cost_estimate": 0.11},
      {"provider": "groq", "status": "complete", "rtf": 0.3, "audio_s": 3600},
      {"provider": "openai", "status": "failed", "error_code": "auth_error", "retries": 2, "audio_s": 999},
      {"status": "cancelled", "error_code": "cancelled"},
    ]
    out = metrics.summarize(entries)
    total = out["total"]
    assert (total["jobs"], total["completed"], total["failed"], total["cancelled"]) == (4, 2, 1, 1)
    assert total["audio_hours"] == 2.0 and total["silence_trimmed_hours"] == 0.1
    assert total["rtf_p50"] == 0.2 and total["retries"] == 3
    assert total["fillers_removed"] == 3 and total["cost_estimate"] == 0.11
    assert set(out["providers"]) == {"groq", "openai", "unknown"}
    assert out["error_codes"] == {"auth_error": 1, "cancelled": 1}


# --- progress ----------------------------------------------------------------------------------


@pytest.fixture
def clean_hub():
  progress._SUBSCRIBERS.clear()
  progress._LATEST.clear()
  yield
  progress._SUBSCRIBERS.clear()
  progress._LATEST.clear()


class TestProgress:
  def test_format_eta(self):
    assert progress.format_eta(None) is None
    assert progress.format_eta(3) == "unos segundos"
    assert progress.format_eta(42) == "~42 s"
    assert progress.format_eta(125) == "~2 min 5 s"

  def test_stage_to_percent(self):
    assert progress.stage_to_percent("transcribing", 0.5) == 50
    assert progress.stage_to_percent("transcribing", 2) == 80
    assert progress.stage_to_percent("unknown", 0.5) == 0

  def test_is_stream_finished(self):
    assert not progress.is_stream_finished({"stage": "transcribing"})
    assert progress.is_stream_finished({"stage": "failed"})
    assert not progress.is_stream_finished({"stage": "complete", "summary_status": "running"})
    assert progress.is_stream_finished({"stage": "complete", "summary_status": "done"})

  def test_hub_subscribe_publish_unsubscribe(self, clean_hub):
    q = progress.subscribe("j")
    progress.publish("j", {"seq": 1, "stage": "transcribing"})
    assert q.get_nowait()["seq"] == 1
    assert progress.latest("j")["seq"] == 1
    progress.unsubscribe("j", q)
    assert "j" not in progress._SUBSCRIBERS
    progress.unsubscribe("missing", q)  # no-op
    progress.forget("j")
    assert progress.latest("j") is None

  def test_publish_drops_oldest_when_full(self, clean_hub):
    q = progress.subscribe("j")
    for i in range(101):
      progress.publish("j", {"seq": i, "stage": "transcribing"})
    assert q.qsize() == 100
    assert q.get_nowait()["seq"] == 1

  def test_publish_terminal_without_loop(self, clean_hub):
    progress.publish("j", {"seq": 1, "stage": "complete", "summary_status": "done"})
    assert progress.latest("j")["seq"] == 1

  @pytest.mark.asyncio
  async def test_terminal_snapshot_expires(self, clean_hub, monkeypatch):
    monkeypatch.setattr(progress, "_RETENTION_S", 0.01)
    progress.publish("j", {"seq": 5, "stage": "failed"})
    progress.publish("k", {"seq": 1, "stage": "failed"})
    progress.subscribe("k")  # subscribed jobs are kept
    await asyncio.sleep(0.05)
    assert progress.latest("j") is None
    assert progress.latest("k") is not None

  @pytest.mark.asyncio
  async def test_reporter_monotonic_eta_and_persist(self, clean_hub, monkeypatch):
    persisted: list[dict] = []

    async def persist(snap):
      persisted.append(snap)

    clock = {"t": 1000.0}
    monkeypatch.setattr(progress.time, "monotonic", lambda: clock["t"])
    rep = progress.ProgressReporter("j", media_id="m", title="T", model_info="W", persist=persist, initial={"seq": 7})
    assert rep.audio_fraction == 0.0
    snap = await rep.update("transcribing", 0.5, "hola", chunks_done=1)
    assert snap["progress"] == 50 and snap["seq"] == 8 and snap["message"] == "hola" and snap["chunks_done"] == 1
    assert snap["eta"] is None  # no work measured yet
    # Progress never goes backwards.
    snap = await rep.update("preprocessing", 0.0)
    assert snap["progress"] == 50
    rep.set_audio_work(100.0, 10.0)
    clock["t"] += 10
    rep.add_audio_done(20.0)
    assert rep.audio_fraction == 0.3
    snap = await rep.update("transcribing", 0.3)
    # rate 2 audio-s / s, 70 s remaining -> 35 + 8
    assert snap["eta_seconds"] == 43 and snap["eta"] == "~43 s"
    rep.add_audio_done(1000)
    assert rep.audio_fraction == 1.0
    snap = await rep.update("cleaning", 0.0)
    assert snap["eta_seconds"] == 8
    snap = await rep.update("complete", 1.0)
    assert snap["eta_seconds"] == 0 and snap["progress"] == 100
    # stage changes force persistence; repeated stage within 5 s is throttled.
    count = len(persisted)
    await rep.update("complete", 1.0)  # terminal -> forced
    assert len(persisted) == count + 1
    await rep.update("custom", 0.0)
    await rep.update("custom", 0.1)
    assert len(persisted) == count + 2
    clock["t"] += 6
    await rep.update("custom", 0.2)
    assert len(persisted) == count + 3

  @pytest.mark.asyncio
  async def test_reporter_persist_failure_is_swallowed(self, clean_hub):
    async def persist(snap):
      raise RuntimeError("db down")

    rep = progress.ProgressReporter("j", media_id="m", title="T", model_info="W", persist=persist)
    snap = await rep.update("queued")
    assert snap["stage"] == "queued"


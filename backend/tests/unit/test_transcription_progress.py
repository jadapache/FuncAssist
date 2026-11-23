from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.exceptions import FFmpegError
from app.features.transcription import progress
from app.features.transcription.errors import TranscriptionJobError, classify_exception, error_from_status, is_transient
from app.features.transcription.media import parse_silencedetect, silence_threshold_db
from app.features.transcription.progress import ProgressReporter, format_eta, is_stream_finished, stage_to_percent


class TestProgressContract:
  def test_stage_ranges(self):
    assert stage_to_percent("preprocessing", 0.0) == 10
    assert stage_to_percent("transcribing", 0.5) == 50
    assert stage_to_percent("complete", 1.0) == 100

  @pytest.mark.asyncio
  async def test_progress_is_monotonic_and_published(self):
    persisted: list[dict] = []

    async def _persist(snapshot):
      persisted.append(snapshot)

    reporter = ProgressReporter("job-mono", media_id="job-mono", title="T", model_info="M", persist=_persist)
    queue = progress.subscribe("job-mono")
    try:
      first = await reporter.update("transcribing", 0.5, "mitad")
      second = await reporter.update("preprocessing", 0.2, "tick tardío")
      assert first["progress"] == 50
      assert second["progress"] == 50  # never goes back
      assert second["seq"] == first["seq"] + 1
      assert queue.qsize() == 2
      assert persisted[0]["stage"] == "transcribing"
    finally:
      progress.unsubscribe("job-mono", queue)

  @pytest.mark.asyncio
  async def test_eta_requires_measured_throughput(self):
    reporter = ProgressReporter("job-eta", media_id="job-eta", title="T", model_info="M")
    reporter.set_audio_work(600.0)
    snap = await reporter.update("transcribing", 0.0)
    assert snap["eta_seconds"] is None and snap["eta"] is None
    reporter._work_started -= 10  # 10 s elapsed
    reporter.add_audio_done(300.0)  # 300 s of audio in 10 s -> 30x
    snap = await reporter.update("transcribing", reporter.audio_fraction)
    assert snap["eta_seconds"] == pytest.approx(10 + progress.POST_TRANSCRIPTION_S, abs=1)

  def test_stream_finishes_after_summary(self):
    assert not is_stream_finished({"stage": "transcribing"})
    assert not is_stream_finished({"stage": "complete", "summary_status": "running"})
    assert is_stream_finished({"stage": "complete", "summary_status": "done"})
    assert is_stream_finished({"stage": "failed"})

  def test_format_eta(self):
    assert format_eta(None) is None
    assert format_eta(3) == "unos segundos"
    assert format_eta(125) == "~2 min 5 s"


class TestErrors:
  @pytest.mark.parametrize(
    "status, code, retryable",
    [(401, "auth_error", False), (413, "file_too_large", False), (429, "rate_limit", True), (503, "provider_unavailable", True)],
  )
  def test_status_mapping(self, status, code, retryable):
    err = error_from_status(status, "detail")
    assert err.code == code and err.retryable is retryable

  def test_classify(self):
    assert classify_exception(httpx.ReadTimeout("slow")).code == "timeout"
    assert classify_exception(FFmpegError("bad")).code == "corrupt_media"
    assert classify_exception(asyncio.CancelledError()).code == "cancelled"
    assert classify_exception(RuntimeError("x")).code == "internal"
    assert is_transient(TranscriptionJobError("rate_limit"))
    assert not is_transient(TranscriptionJobError("auth_error"))


class TestSilenceParsing:
  def test_parse_silencedetect(self):
    stderr = (
      "[silencedetect @ 0x1] silence_start: 3.5\n"
      "[silencedetect @ 0x1] silence_end: 7.25 | silence_duration: 3.75\n"
      "[silencedetect @ 0x1] silence_start: 55\n"
    )
    assert parse_silencedetect(stderr, 60.0) == [(3.5, 7.25), (55.0, 60.0)]

  def test_threshold_is_clamped(self):
    assert silence_threshold_db(None) == -35.0
    assert silence_threshold_db(-70.0) == -50.0
    assert silence_threshold_db(-40.0) == -34.0
    assert silence_threshold_db(-10.0) == -25.0

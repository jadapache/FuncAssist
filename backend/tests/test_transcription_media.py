"""ffmpeg/ffprobe helper tests. Subprocesses and ffmpeg are faked."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.core.exceptions import AudioAnalysisError, FFmpegError
from app.features.transcription import media


class FakeStream:
  def __init__(self, data: bytes = b"", hang: bool = False):
    self._lines = data.splitlines(keepends=True)
    self._data = data
    self._hang = hang

  async def readline(self):
    if self._hang:
      await asyncio.sleep(30)
    return self._lines.pop(0) if self._lines else b""

  async def read(self):
    if self._hang:
      await asyncio.sleep(30)
    return self._data


class FakeProc:
  def __init__(self, out=b"", err=b"", code=0, hang=False):
    self.stdout, self.stderr = FakeStream(out, hang), FakeStream(err, hang)
    self.returncode = None
    self._code = code
    self.killed = False

  async def wait(self):
    self.returncode = self._code
    return self._code

  def kill(self):
    self.killed = True


def _spawn(monkeypatch, proc: FakeProc) -> FakeProc:
  async def fake_exec(*args, **kwargs):
    return proc

  monkeypatch.setattr(media.asyncio, "create_subprocess_exec", fake_exec)
  return proc


# --- run_process (fake subprocess: the app forces the selector loop on Windows) ----------------


@pytest.mark.asyncio
async def test_run_process_collects_stdout_stderr_and_code(monkeypatch):
  _spawn(monkeypatch, FakeProc(out=b"a\nb\n", err=b"oops", code=3))
  code, out, err = await media.run_process(["x"], timeout=30)
  assert (code, out, err) == (3, "a\nb", "oops")


@pytest.mark.asyncio
async def test_run_process_streams_lines_to_callback(monkeypatch):
  _spawn(monkeypatch, FakeProc(out=b"x\ny\n"))
  lines: list[str] = []
  code, out, _ = await media.run_process(["x"], timeout=30, on_stdout_line=lines.append)
  assert code == 0 and out == ""
  assert lines == ["x", "y"]


@pytest.mark.asyncio
async def test_run_process_timeout_kills_process(monkeypatch):
  proc = _spawn(monkeypatch, FakeProc(hang=True))
  with pytest.raises(asyncio.TimeoutError):
    await media.run_process(["x"], timeout=0.2)
  assert proc.killed


@pytest.mark.asyncio
async def test_run_process_cancellation_kills_and_propagates(monkeypatch):
  proc = _spawn(monkeypatch, FakeProc(hang=True))
  task = asyncio.create_task(media.run_process(["x"], timeout=60))
  await asyncio.sleep(0.1)
  task.cancel()
  with pytest.raises(asyncio.CancelledError):
    await task
  assert proc.killed


def test_kill_ignores_finished_and_missing_processes():
  class Done:
    returncode = 0

    def kill(self):
      raise AssertionError("must not kill a finished process")

  class Gone:
    returncode = None

    def kill(self):
      raise ProcessLookupError

  media._kill(Done())
  media._kill(Gone())


# --- find_ffprobe -------------------------------------------------------------------------------


def test_find_ffprobe_prefers_path(monkeypatch):
  monkeypatch.setattr(media.shutil, "which", lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None)
  assert media.find_ffprobe() == "/usr/bin/ffprobe"


def test_find_ffprobe_uses_ffmpeg_sibling(monkeypatch, tmp_path):
  ffmpeg = tmp_path / "ffmpeg.exe"
  ffprobe = tmp_path / "ffprobe.exe"
  ffmpeg.write_bytes(b"x")
  ffprobe.write_bytes(b"x")
  monkeypatch.setattr(media.shutil, "which", lambda name: None)
  monkeypatch.setattr(media, "get_ffmpeg_binary", lambda: str(ffmpeg))
  assert media.find_ffprobe() == str(ffprobe)


def test_find_ffprobe_none_when_unavailable(monkeypatch, tmp_path):
  monkeypatch.setattr(media.shutil, "which", lambda name: None)
  monkeypatch.setattr(media, "get_ffmpeg_binary", lambda: None)
  assert media.find_ffprobe() is None
  monkeypatch.setattr(media, "get_ffmpeg_binary", lambda: str(tmp_path / "ffmpeg"))
  assert media.find_ffprobe() is None


# --- probe_duration -----------------------------------------------------------------------------


@pytest.fixture
def audio_file(tmp_path) -> Path:
  path = tmp_path / "a.mp3"
  path.write_bytes(b"data")
  return path


def _fake_run(result=None, error=None):
  async def run(args, *, timeout, on_stdout_line=None):
    if error:
      raise error
    return result

  return run


@pytest.mark.asyncio
async def test_probe_duration_file_missing(tmp_path):
  with pytest.raises(AudioAnalysisError):
    await media.probe_duration(tmp_path / "nope.mp3")


@pytest.mark.asyncio
async def test_probe_duration_without_ffprobe(monkeypatch, audio_file):
  monkeypatch.setattr(media, "find_ffprobe", lambda: None)
  with pytest.raises(AudioAnalysisError):
    await media.probe_duration(audio_file)


@pytest.mark.asyncio
async def test_probe_duration_ok(monkeypatch, audio_file):
  monkeypatch.setattr(media, "find_ffprobe", lambda: "ffprobe")
  monkeypatch.setattr(media, "run_process", _fake_run((0, "codec_type=audio\nduration=12.5", "")))
  assert await media.probe_duration(audio_file) == 12.5


@pytest.mark.parametrize(
  "result,error",
  [
    ((1, "", "invalid data"), None),
    ((0, "duration=10", ""), None),  # no audio stream
    ((0, "codec_type=audio", ""), None),  # no duration
    ((0, "codec_type=audio\nduration=0.0", ""), None),
    (None, asyncio.TimeoutError()),
  ],
)
@pytest.mark.asyncio
async def test_probe_duration_errors(monkeypatch, audio_file, result, error):
  monkeypatch.setattr(media, "find_ffprobe", lambda: "ffprobe")
  monkeypatch.setattr(media, "run_process", _fake_run(result, error))
  with pytest.raises(AudioAnalysisError):
    await media.probe_duration(audio_file)


# --- progress parsing ---------------------------------------------------------------------------


@pytest.mark.parametrize(
  "line,expected",
  [("out_time_us=2500000", 2.5), ("out_time_ms=1000000", 1.0), ("out_time_us=N/A", None),
   ("out_time=00:00:01", None), ("frame=3", None)],
)
def test_parse_progress_seconds(line, expected):
  assert media._parse_progress_seconds(line) == expected


# --- extract_audio ------------------------------------------------------------------------------


@pytest.fixture
def fake_ffmpeg(monkeypatch):
  monkeypatch.setattr(media, "ensure_ffmpeg_available", lambda: "ffmpeg")


@pytest.mark.asyncio
async def test_extract_audio_success_reports_progress(monkeypatch, fake_ffmpeg, tmp_path):
  dest = tmp_path / "out" / "audio.wav"
  seen: list[float] = []

  async def run(args, *, timeout, on_stdout_line=None):
    assert timeout == 300.0
    on_stdout_line("out_time_us=5000000")
    on_stdout_line("out_time_us=99000000")  # clamped to 1.0
    on_stdout_line("garbage")
    Path(args[-1]).write_bytes(b"w" * 200)
    return 0, "", ""

  monkeypatch.setattr(media, "run_process", run)
  result = await media.extract_audio(tmp_path / "in.mp4", dest, 10.0, on_progress=seen.append)
  assert result == dest and dest.read_bytes() == b"w" * 200
  assert seen == [0.5, 1.0]
  assert not dest.with_suffix(".tmp.wav").exists()


@pytest.mark.asyncio
async def test_extract_audio_timeout_scales_with_duration(monkeypatch, fake_ffmpeg, tmp_path):
  seen = {}

  async def run(args, *, timeout, on_stdout_line=None):
    seen["timeout"] = timeout
    Path(args[-1]).write_bytes(b"w" * 200)
    return 0, "", ""

  monkeypatch.setattr(media, "run_process", run)
  await media.extract_audio(tmp_path / "in.mp4", tmp_path / "a.wav", 4000.0)
  assert seen["timeout"] == 2000.0


@pytest.mark.parametrize("write_size", [None, 10])
@pytest.mark.asyncio
async def test_extract_audio_failure_cleans_tmp(monkeypatch, fake_ffmpeg, tmp_path, write_size):
  async def run(args, *, timeout, on_stdout_line=None):
    if write_size:
      Path(args[-1]).write_bytes(b"x" * write_size)
    return 1, "", "e" * 3000

  monkeypatch.setattr(media, "run_process", run)
  dest = tmp_path / "a.wav"
  with pytest.raises(FFmpegError):
    await media.extract_audio(tmp_path / "in.mp4", dest, 10.0)
  assert not dest.exists() and not dest.with_suffix(".tmp.wav").exists()


# --- measure_noise_floor ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_measure_noise_floor_percentile(monkeypatch, fake_ffmpeg, tmp_path):
  async def run(args, *, timeout, on_stdout_line=None):
    for value in ["-60", "-20", "-inf", "bad", "-40", "-30", "-50", "-10", "-70", "-25", "-35", "-45"]:
      on_stdout_line(f"lavfi.astats.Overall.RMS_level={value}" if value != "bad" else "RMS_level=bad")
    on_stdout_line("unrelated")
    return 0, "", ""

  monkeypatch.setattr(media, "run_process", run)
  # 10 finite values sorted ascending; index max(0, int(10*0.1)-1) = 0 -> the lowest level
  assert await media.measure_noise_floor(tmp_path / "a.wav") == -70.0


@pytest.mark.asyncio
async def test_measure_noise_floor_none_without_levels(monkeypatch, fake_ffmpeg, tmp_path):
  monkeypatch.setattr(media, "run_process", _fake_run((0, "", "")))
  assert await media.measure_noise_floor(tmp_path / "a.wav") is None


@pytest.mark.asyncio
async def test_measure_noise_floor_timeout_returns_none(monkeypatch, fake_ffmpeg, tmp_path):
  monkeypatch.setattr(media, "run_process", _fake_run(error=asyncio.TimeoutError()))
  assert await media.measure_noise_floor(tmp_path / "a.wav") is None


# --- silence detection --------------------------------------------------------------------------


@pytest.mark.parametrize(
  "noise,expected",
  [(None, -35.0), (-80.0, -50.0), (-40.0, -34.0), (-10.0, -25.0)],
)
def test_silence_threshold_db(noise, expected):
  assert media.silence_threshold_db(noise) == expected


def test_parse_silencedetect_pairs_and_clamps():
  stderr = "\n".join([
    "[silencedetect] silence_start: -0.05",
    "[silencedetect] silence_end: 2.0 | silence_duration: 2.0",
    "[silencedetect] silence_end: 9.0 | silence_duration: 1",  # end without start is ignored
    "[silencedetect] silence_start: 5.0",
    "[silencedetect] silence_end: 50.0 | silence_duration: 45",
  ])
  assert media.parse_silencedetect(stderr, 20.0) == [(0.0, 2.0), (5.0, 20.0)]


def test_parse_silencedetect_trailing_silence_without_end():
  assert media.parse_silencedetect("silence_start: 8.0", 10.0) == [(8.0, 10.0)]
  assert media.parse_silencedetect("silence_start: 12.0", 10.0) == []


@pytest.mark.asyncio
async def test_detect_silences(monkeypatch, fake_ffmpeg, tmp_path):
  captured = {}

  async def run(args, *, timeout, on_stdout_line=None):
    captured["args"] = args
    return 0, "", "silence_start: 1.0\nsilence_end: 2.5"

  monkeypatch.setattr(media, "run_process", run)
  assert await media.detect_silences(tmp_path / "a.wav", -30.0, 0.8, 10.0) == [(1.0, 2.5)]
  assert "silencedetect=noise=-30.0dB:d=0.80" in captured["args"]


@pytest.mark.asyncio
async def test_detect_silences_failure(monkeypatch, fake_ffmpeg, tmp_path):
  monkeypatch.setattr(media, "run_process", _fake_run((1, "", "bad")))
  with pytest.raises(FFmpegError):
    await media.detect_silences(tmp_path / "a.wav", -30.0, 0.8, 10.0)


# --- export_regions / export_clip ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_regions_builds_graph_and_cleans_script(monkeypatch, fake_ffmpeg, tmp_path):
  dest = tmp_path / "chunks" / "c1.mp3"
  seen = {}

  async def run(args, *, timeout, on_stdout_line=None):
    script = Path(args[args.index("-filter_complex_script") + 1])
    seen["graph"] = script.read_text(encoding="utf-8")
    Path(args[-1]).write_bytes(b"mp3")
    return 0, "", ""

  monkeypatch.setattr(media, "run_process", run)
  assert await media.export_regions(tmp_path / "a.wav", [(0, 1.5), (3, 4)], dest) == dest
  assert "atrim=start=0.000:end=1.500" in seen["graph"]
  assert "[r0][r1]concat=n=2:v=0:a=1[out]" in seen["graph"]
  assert dest.read_bytes() == b"mp3"
  assert not dest.with_suffix(".filter.txt").exists()
  assert not dest.with_suffix(".tmp.mp3").exists()


@pytest.mark.asyncio
async def test_export_regions_requires_regions(fake_ffmpeg, tmp_path):
  with pytest.raises(FFmpegError):
    await media.export_regions(tmp_path / "a.wav", [], tmp_path / "c.mp3")


@pytest.mark.parametrize("write", [False, True])
@pytest.mark.asyncio
async def test_export_regions_failure(monkeypatch, fake_ffmpeg, tmp_path, write):
  async def run(args, *, timeout, on_stdout_line=None):
    if write:
      Path(args[-1]).write_bytes(b"")  # empty output is a failure even with code 0
    return (0 if write else 1), "", "err"

  monkeypatch.setattr(media, "run_process", run)
  dest = tmp_path / "c.mp3"
  with pytest.raises(FFmpegError):
    await media.export_regions(tmp_path / "a.wav", [(0, 1)], dest)
  assert not dest.exists() and not dest.with_suffix(".tmp.mp3").exists()
  assert not dest.with_suffix(".filter.txt").exists()


@pytest.mark.asyncio
async def test_export_clip_delegates(monkeypatch, tmp_path):
  calls = []

  async def fake_export(wav, regions, dest):
    calls.append((wav, list(regions), dest))
    return dest

  monkeypatch.setattr(media, "export_regions", fake_export)
  dest = tmp_path / "clip.mp3"
  assert await media.export_clip(tmp_path / "a.wav", 1.0, 2.0, dest) == dest
  assert calls == [(tmp_path / "a.wav", [(1.0, 2.0)], dest)]

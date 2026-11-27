"""FFmpeg discovery, audio extraction and output validation, with the subprocesses replaced."""

import logging
import os
import subprocess
from types import SimpleNamespace

import pytest

from app.core.exceptions import FFmpegError
from app.features.transcription import ffmpeg_utils as fu


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
  monkeypatch.setattr(fu, "_CACHED_FFMPEG_PATH", None)
  monkeypatch.setattr(fu, "BIN_DIR", tmp_path / "bin")
  monkeypatch.setattr(fu.shutil, "which", lambda name: None)
  monkeypatch.setenv("PATH", "/usr/bin")


def _binary(directory, size=20000, name="ffmpeg"):
  directory.mkdir(parents=True, exist_ok=True)
  path = directory / name
  path.write_bytes(b"x" * size)
  return path


# --- discovery ----------------------------------------------------------------------


def test_bundled_binary_is_used_and_its_directory_goes_first_on_the_path(tmp_path):
  target = _binary(tmp_path / "bin")
  assert fu.get_ffmpeg_binary() == str(target.resolve())
  assert os.environ["PATH"] == f"{tmp_path / 'bin'}{os.pathsep}/usr/bin"
  fu.get_ffmpeg_binary()
  assert os.environ["PATH"].count(str(tmp_path / "bin")) == 1


def test_bundled_binary_is_looked_up_by_the_platform_name(tmp_path, monkeypatch):
  _binary(tmp_path / "bin", name="ffmpeg.exe")
  monkeypatch.setattr(fu, "sys", SimpleNamespace(platform="win32"))
  assert fu.get_ffmpeg_binary().endswith("ffmpeg.exe")
  monkeypatch.setattr(fu, "_CACHED_FFMPEG_PATH", None)
  monkeypatch.setattr(fu, "sys", SimpleNamespace(platform="linux"))
  assert fu.get_ffmpeg_binary() is None


def test_a_truncated_bundled_binary_is_ignored(tmp_path):
  _binary(tmp_path / "bin", size=10000)
  assert fu.get_ffmpeg_binary() is None
  _binary(tmp_path / "bin", size=10001)
  assert fu.get_ffmpeg_binary() is not None


def test_the_system_binary_is_the_fallback_and_the_exe_name_is_tried_too(tmp_path, monkeypatch):
  system = _binary(tmp_path / "sys")
  monkeypatch.setattr(fu.shutil, "which", lambda name: str(system) if name == "ffmpeg" else None)
  assert fu.get_ffmpeg_binary() == str(system.resolve())
  monkeypatch.setattr(fu, "_CACHED_FFMPEG_PATH", None)
  monkeypatch.setattr(fu.shutil, "which", lambda name: str(system) if name == "ffmpeg.exe" else None)
  assert fu.get_ffmpeg_binary() == str(system.resolve())


def test_a_system_binary_that_does_not_exist_is_not_used(tmp_path, monkeypatch):
  monkeypatch.setattr(fu.shutil, "which", lambda name: str(tmp_path / "ghost"))
  assert fu.get_ffmpeg_binary() is None


def test_the_found_binary_is_cached_until_it_disappears(tmp_path):
  first = _binary(tmp_path / "bin")
  assert fu.get_ffmpeg_binary() == str(first.resolve())
  first.unlink()
  assert fu.get_ffmpeg_binary() is None


def test_ensure_available_raises_with_install_hints_when_missing(caplog):
  with caplog.at_level(logging.ERROR), pytest.raises(FFmpegError, match="brew install ffmpeg"):
    fu.ensure_ffmpeg_available()
  assert any("FFmpeg is not installed" in r.getMessage() for r in caplog.records)
  assert fu.ensure_ffmpeg_in_user_data() is None


def test_ensure_available_returns_the_binary(tmp_path):
  target = _binary(tmp_path / "bin")
  assert fu.ensure_ffmpeg_available() == str(target.resolve()) == fu.ensure_ffmpeg_in_user_data()


# --- extraction ---------------------------------------------------------------------


class _Run:
  def __init__(self, *replies):
    self.replies, self.calls = list(replies), []

  def __call__(self, cmd, **kwargs):
    self.calls.append((cmd, kwargs))
    reply = self.replies.pop(0)
    if isinstance(reply, Exception):
      raise reply
    return reply


def _done(returncode=0, stdout="", stderr=""):
  return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def ffmpeg(tmp_path, monkeypatch):
  _binary(tmp_path / "bin")
  run = _Run()
  monkeypatch.setattr(fu.subprocess, "run", run)
  return run


def test_wav_files_are_returned_as_they_are(tmp_path):
  source = tmp_path / "a.WAV"
  assert fu.extract_audio_track(source, tmp_path / "out.wav") == (source, True)


def test_other_media_is_converted_to_16khz_mono_pcm(tmp_path, ffmpeg, caplog):
  ffmpeg.replies = [_done()]
  out = tmp_path / "out.wav"
  with caplog.at_level(logging.INFO):
    assert fu.extract_audio_track(tmp_path / "a.mp4", out, validate=False) == (out, True)
  cmd, kwargs = ffmpeg.calls[0]
  assert cmd[1:] == ["-y", "-i", str(tmp_path / "a.mp4"), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(out)]
  assert kwargs == {"capture_output": True, "text": True, "timeout": 1800}
  assert any("Successfully extracted audio: a.mp4 → out.wav" in r.getMessage() for r in caplog.records)


def test_extraction_validates_the_output_by_default(tmp_path, ffmpeg, monkeypatch):
  ffmpeg.replies = [_done()]
  seen = []
  monkeypatch.setattr(fu, "_validate_output_wav", lambda out, src: seen.append((out, src)))
  out = tmp_path / "out.wav"
  fu.extract_audio_track(tmp_path / "a.mp3", out)
  assert seen == [(out, tmp_path / "a.mp3")]


def test_a_failed_conversion_carries_stderr_and_return_code(tmp_path, ffmpeg, caplog):
  ffmpeg.replies = [_done(returncode=1, stderr="bad codec")]
  with caplog.at_level(logging.ERROR), pytest.raises(FFmpegError) as raised:
    fu.extract_audio_track(tmp_path / "a.mp4", tmp_path / "o.wav")
  assert "FFmpeg conversion failed (exit code: 1)" in str(raised.value)
  assert raised.value.stderr == "bad codec" and raised.value.returncode == 1
  assert any("FFmpeg conversion failed: bad codec" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("error", [subprocess.TimeoutExpired("ffmpeg", 1), TimeoutError()])
def test_a_timeout_is_reported_as_such(tmp_path, ffmpeg, caplog, error):
  ffmpeg.replies = [error]
  with caplog.at_level(logging.ERROR), pytest.raises(FFmpegError, match="FFmpeg audio extraction timeout"):
    fu.extract_audio_track(tmp_path / "a.mp4", tmp_path / "o.wav")
  assert any("FFmpeg audio extraction timeout" in r.getMessage() for r in caplog.records)


def test_any_other_failure_is_wrapped(tmp_path, ffmpeg, caplog):
  ffmpeg.replies = [OSError("disk gone")]
  with caplog.at_level(logging.ERROR), pytest.raises(FFmpegError, match="Unexpected error during FFmpeg audio extraction: disk gone"):
    fu.extract_audio_track(tmp_path / "a.mp4", tmp_path / "o.wav")
  assert any("Unexpected error during" in r.getMessage() for r in caplog.records)


def test_missing_ffmpeg_stops_extraction_before_running_anything(tmp_path, monkeypatch):
  run = _Run()
  monkeypatch.setattr(fu.subprocess, "run", run)
  with pytest.raises(FFmpegError, match="not installed"):
    fu.extract_audio_track(tmp_path / "a.mp4", tmp_path / "o.wav")
  assert run.calls == []


# --- validation ---------------------------------------------------------------------


@pytest.fixture
def probe(tmp_path, monkeypatch):
  run = _Run()
  monkeypatch.setattr(fu.subprocess, "run", run)
  monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None)
  out = tmp_path / "out.wav"
  out.write_bytes(b"w" * 2000)
  run.out = out
  return run


def test_a_missing_output_is_an_error(tmp_path):
  with pytest.raises(FFmpegError, match="Output file was not created"):
    fu._validate_output_wav(tmp_path / "none.wav", tmp_path / "src")


def test_an_empty_output_is_an_error(tmp_path):
  empty = tmp_path / "e.wav"
  empty.write_bytes(b"")
  with pytest.raises(FFmpegError, match=r"Output file is empty \(0 bytes\)"):
    fu._validate_output_wav(empty, tmp_path / "src")


def test_a_tiny_output_only_warns(tmp_path, caplog):
  tiny = tmp_path / "t.wav"
  tiny.write_bytes(b"x")
  with caplog.at_level(logging.WARNING):
    fu._validate_output_wav(tiny, tmp_path / "src")
  messages = [r.getMessage() for r in caplog.records]
  assert any("Output file is very small (1 bytes)" in m for m in messages)
  assert any("ffprobe not available" in m for m in messages)


def test_a_one_kilobyte_output_is_not_suspicious(tmp_path, caplog):
  exact = tmp_path / "k.wav"
  exact.write_bytes(b"x" * 1000)
  with caplog.at_level(logging.WARNING):
    fu._validate_output_wav(exact, tmp_path / "src")
  assert not any("very small" in r.getMessage() for r in caplog.records)


def test_a_probe_that_reports_a_duration_passes(probe, tmp_path):
  probe.replies = [_done(stdout="12.5\n")]
  fu._validate_output_wav(probe.out, tmp_path / "src")
  cmd, kwargs = probe.calls[0]
  assert cmd[0] == "/usr/bin/ffprobe" and cmd[-1] == str(probe.out) and "format=duration" in cmd
  assert kwargs == {"capture_output": True, "text": True, "timeout": 10}


def test_a_probe_that_fails_reports_its_error(probe, tmp_path):
  probe.replies = [_done(returncode=1, stderr="invalid data")]
  with pytest.raises(FFmpegError, match="Output WAV validation failed: invalid data"):
    fu._validate_output_wav(probe.out, tmp_path / "src")


@pytest.mark.parametrize("stdout, message", [
  ("0", "zero or negative duration: 0.0s"),
  ("-3", "zero or negative duration: -3.0s"),
  ("N/A", "Could not parse output WAV duration: N/A"),
])
def test_an_unusable_duration_is_an_error(probe, tmp_path, stdout, message):
  probe.replies = [_done(stdout=stdout)]
  with pytest.raises(FFmpegError, match=message):
    fu._validate_output_wav(probe.out, tmp_path / "src")


def test_a_hanging_probe_is_an_error(probe, tmp_path):
  probe.replies = [subprocess.TimeoutExpired("ffprobe", 10)]
  with pytest.raises(FFmpegError, match="Output WAV validation timeout"):
    fu._validate_output_wav(probe.out, tmp_path / "src")


def test_a_tiny_positive_duration_is_valid(probe, tmp_path):
  probe.replies = [_done(stdout="0.001")]
  fu._validate_output_wav(probe.out, tmp_path / "src")

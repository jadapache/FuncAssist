"""Local file picker tests: native dialog subprocess handling and local-root path inspection."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from app.features.transcription import local_picker


@pytest.fixture
def local_root(tmp_path, monkeypatch):
  root = tmp_path / "recordings"
  root.mkdir()
  monkeypatch.setenv("TRANSCRIPTION_LOCAL_ROOTS", str(root))
  return root


# --- inspect_local_file -------------------------------------------------------------------------


def test_inspect_rejects_path_outside_roots(local_root, tmp_path):
  outside = tmp_path / "secret.mp3"
  outside.write_bytes(b"x")
  res = local_picker.inspect_local_file(str(outside))
  assert res == {"ok": False, "exists": False, "error": "Ruta local no permitida."}


def test_inspect_rejects_traversal_out_of_root(local_root, tmp_path):
  (tmp_path / "secret.mp3").write_bytes(b"x")
  res = local_picker.inspect_local_file(str(local_root / ".." / "secret.mp3"))
  assert res["ok"] is False and res["exists"] is False


def test_inspect_rejects_when_no_roots_configured(monkeypatch, tmp_path):
  monkeypatch.delenv("TRANSCRIPTION_LOCAL_ROOTS", raising=False)
  f = tmp_path / "a.mp3"
  f.write_bytes(b"x")
  assert local_picker.inspect_local_file(str(f))["ok"] is False


def test_inspect_missing_file(local_root):
  res = local_picker.inspect_local_file(str(local_root / "nope.mp3"))
  assert res["ok"] is False and res["exists"] is False
  assert "no existe" in res["error"]


def test_inspect_unsupported_extension(local_root):
  f = local_root / "notes.txt"
  f.write_bytes(b"hello")
  res = local_picker.inspect_local_file(str(f))
  assert res["ok"] is False and res["exists"] is True
  assert "no soportado" in res["error"]


def test_inspect_empty_file(local_root):
  f = local_root / "empty.mp3"
  f.write_bytes(b"")
  res = local_picker.inspect_local_file(str(f))
  assert res["ok"] is False and res["exists"] is True
  assert "vacío" in res["error"]


@pytest.mark.parametrize("name,is_video", [("talk.mp3", False), ("talk.WAV", False), ("talk.mp4", True), ("talk.MKV", True)])
def test_inspect_valid_file(local_root, name, is_video):
  f = local_root / name
  f.write_bytes(b"x" * 2048)
  res = local_picker.inspect_local_file(f'  "{f}"  ')  # surrounding quotes/spaces are tolerated
  assert res["ok"] is True and res["exists"] is True
  assert res["filename"] == name
  assert res["size_bytes"] == 2048
  assert res["size_formatted"] == "2.0 KB"
  assert res["is_video"] is is_video


# --- native dialog ------------------------------------------------------------------------------


def _patch_run(monkeypatch, *, stdout="", error=None):
  calls = []

  def fake_run(cmd, **kwargs):
    calls.append((cmd, kwargs))
    if error:
      raise error
    return SimpleNamespace(stdout=stdout)

  monkeypatch.setattr(local_picker.subprocess, "run", fake_run)
  return calls


def test_dialog_returns_resolved_selected_file(monkeypatch, tmp_path):
  f = tmp_path / "meeting.mp3"
  f.write_bytes(b"x")
  calls = _patch_run(monkeypatch, stdout=f"{f}\r\n")
  assert local_picker.open_native_file_dialog_sync() == str(f.resolve())
  cmd, kwargs = calls[0]
  assert cmd[0] == "powershell.exe" and "-Sta" in cmd
  assert local_picker.SUPPORTED_FILTER in cmd[-1]
  assert kwargs["timeout"] == 300


@pytest.mark.parametrize("stdout", ["", "   \n", "C:\\does\\not\\exist.mp3"])
def test_dialog_cancelled_or_missing_returns_none(monkeypatch, stdout):
  _patch_run(monkeypatch, stdout=stdout)
  assert local_picker.open_native_file_dialog_sync() is None


def test_dialog_directory_selection_returns_none(monkeypatch, tmp_path):
  _patch_run(monkeypatch, stdout=str(tmp_path))
  assert local_picker.open_native_file_dialog_sync() is None


def test_dialog_handles_none_stdout(monkeypatch):
  _patch_run(monkeypatch, stdout=None)
  assert local_picker.open_native_file_dialog_sync() is None


@pytest.mark.parametrize("error", [subprocess.TimeoutExpired("powershell.exe", 300), FileNotFoundError("powershell.exe")])
def test_dialog_subprocess_errors_return_none(monkeypatch, error):
  _patch_run(monkeypatch, error=error)
  assert local_picker.open_native_file_dialog_sync() is None


def test_dialog_without_create_no_window_flag(monkeypatch):
  monkeypatch.delattr(local_picker.subprocess, "CREATE_NO_WINDOW", raising=False)
  calls = _patch_run(monkeypatch, stdout="")
  local_picker.open_native_file_dialog_sync()
  assert calls[0][1]["creationflags"] == 0

"""On-disk layout of transcriptions: ids, media lookup, streamed uploads and local-file references."""

import io
import logging
import os

import pytest

from app.features.transcription import storage
from app.features.transcription.errors import TranscriptionJobError


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
  monkeypatch.setattr(storage, "TRANSCRIPTIONS_DIR", tmp_path / "transcriptions")
  (tmp_path / "transcriptions").mkdir()
  for name in ("TRANSCRIPTION_DESKTOP_MODE", "TRANSCRIPTION_LOCAL_ROOTS", "TRANSCRIPTION_MAX_UPLOAD_MB"):
    monkeypatch.delenv(name, raising=False)
  return tmp_path


class Upload:
  def __init__(self, data, filename="clip.mp3"):
    self.filename, self._data = filename, io.BytesIO(data)

  async def read(self, size):
    return self._data.read(size)


def _code(call, *args, **kwargs):
  with pytest.raises(TranscriptionJobError) as raised:
    call(*args, **kwargs)
  return raised.value


# --- ids and folders ----------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "../x", "a/b", "a.b", "x" * 65, "a b", "..", "id\n"])
def test_unsafe_ids_are_rejected(bad):
  error = _code(storage.get_transcription_dir, bad)
  assert error.code == "bad_request" and error.user_message == "Identificador de transcripción no válido."


def test_valid_ids_resolve_inside_the_transcriptions_directory(isolated):
  assert storage.get_transcription_dir("abc-DEF_123") == (isolated / "transcriptions" / "abc-DEF_123").resolve()
  assert storage.get_transcription_dir("x" * 64).name == "x" * 64
  assert storage.chunks_dir("abc") == storage.get_transcription_dir("abc") / "chunks"


def test_a_link_that_leaves_the_directory_is_rejected(isolated):
  outside = isolated / "outside"
  outside.mkdir()
  os.symlink(outside, isolated / "transcriptions" / "escape")
  assert _code(storage.get_transcription_dir, "escape").code == "bad_request"


def test_directories_are_created_with_their_parents(isolated, monkeypatch):
  nested = isolated / "a" / "b" / "transcriptions"
  monkeypatch.setattr(storage, "TRANSCRIPTIONS_DIR", nested)
  monkeypatch.setattr(storage, "APP_TRANSCRIPTIONS_DIR", isolated / "c" / "d")
  monkeypatch.setattr(storage, "ensure_local_dirs", lambda: None)
  storage.ensure_transcription_dirs()
  storage.ensure_transcription_dirs()
  assert nested.is_dir() and (isolated / "c" / "d").is_dir()


def test_hash_and_size_formatting():
  assert storage.get_file_hash(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
  assert [storage.format_size_bytes(n) for n in (0, 1023, 1024, 1024 ** 2 - 1, 1024 ** 2, 1536 * 1024, 1024 ** 3, 3 * 1024 ** 3)] == [
    "0 B", "1023 B", "1.0 KB", "1024.0 KB", "1.0 MB", "1.5 MB", "1.0 GB", "3.0 GB",
  ]


def test_file_validation_checks_the_extension_then_the_size():
  assert storage.validate_file("a.MP3", 1) == (True, None)
  assert storage.validate_file("a.mp4", 10) == (True, None)
  ok, message = storage.validate_file("a.txt", 5)
  assert ok is False and message.startswith("Formato '.txt' no soportado. Formatos admitidos: .aac, .avi")
  assert storage.validate_file("noext", 5)[1].startswith("Formato '' no soportado")
  assert storage.validate_file("a.mp3", 0) == (False, "El archivo está vacío.")
  assert storage.validate_file("a.mp3", -1)[0] is False


# --- finding media ------------------------------------------------------------------


def _folder(isolated, name="t1"):
  folder = isolated / "transcriptions" / name
  folder.mkdir(parents=True, exist_ok=True)
  return folder.resolve()


def test_media_lookup_prefers_the_extracted_audio(isolated):
  folder = _folder(isolated)
  (folder / "media.mp4").write_bytes(b"v")
  assert storage.find_media_file("t1") == folder / "media.mp4"
  (folder / "audio.wav").write_bytes(b"a")
  assert storage.find_media_file("t1") == folder / "audio.wav" and storage.has_media("t1") is True


def test_media_lookup_takes_the_first_supported_media_file_in_order(isolated):
  folder = _folder(isolated)
  (folder / "media.txt").write_bytes(b"x")
  (folder / "media.zzz").mkdir()
  (folder / "media.MP3").write_bytes(b"x")
  (folder / "media.aac").write_bytes(b"x")
  assert storage.find_media_file("t1") == folder / "media.MP3"
  (folder / "media.MP3").unlink()
  assert storage.find_media_file("t1") == folder / "media.aac"
  (folder / "media.aac").unlink()
  assert storage.find_media_file("t1") is None and storage.has_media("t1") is False


def test_media_lookup_without_a_folder_finds_nothing(isolated):
  assert storage.find_media_file("none") is None


def _desktop(monkeypatch, root):
  monkeypatch.setenv("TRANSCRIPTION_DESKTOP_MODE", "1")
  monkeypatch.setenv("TRANSCRIPTION_LOCAL_ROOTS", str(root))


def test_a_registered_local_source_is_found_in_desktop_mode(isolated, monkeypatch):
  root = isolated / "media"
  root.mkdir()
  source = root / "talk.mp3"
  source.write_bytes(b"x")
  record = {"metadata": {"source_path": str(source)}}
  assert storage.find_media_file("none", record) is None
  _desktop(monkeypatch, root)
  assert storage.find_media_file("none", record) == source
  assert storage.find_media_file("none", {"metadata": {}}) is None
  assert storage.find_media_file("none", {}) is None
  assert storage.find_media_file("none", None) is None
  assert storage.find_media_file("none", {"metadata": {"source_path": str(root / "missing.mp3")}}) is None
  elsewhere = isolated / "elsewhere.mp3"
  elsewhere.write_bytes(b"x")
  assert storage.find_media_file("none", {"metadata": {"source_path": str(elsewhere)}}) is None


# --- uploads ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_upload_is_streamed_hashed_and_described(isolated, monkeypatch):
  monkeypatch.setattr(storage, "ensure_local_dirs", lambda: None)
  data = b"a" * (storage.UPLOAD_BLOCK + 10)
  entry = await storage.save_upload(Upload(data, "Sesión.MP3"), "t1", "  Mi reunión ", " nota ")
  folder = _folder(isolated)
  assert (folder / "media.mp3").read_bytes() == data and not list(folder.glob(".*"))
  assert entry["id"] == entry["transcription_id"] == "t1" and entry["path"] == str(folder / "media.mp3")
  assert (entry["original_filename"], entry["filename"], entry["stored_filename"]) == ("Sesión.MP3", "Sesión.MP3", "media.mp3")
  assert entry["size_bytes"] == len(data) and entry["file_size_formatted"] == "1.0 MB"
  assert entry["hash"] == storage.get_file_hash(data) and entry["is_video"] is False
  assert (entry["title"], entry["description"]) == ("Mi reunión", "nota") and entry["created_at"]


@pytest.mark.asyncio
async def test_video_uploads_are_flagged_and_titles_default_to_the_file_name(isolated, monkeypatch):
  monkeypatch.setattr(storage, "ensure_local_dirs", lambda: None)
  entry = await storage.save_upload(Upload(b"v", "movie.mp4"), "t1", "   ")
  assert entry["is_video"] is True and entry["title"] == "movie.mp4" and entry["description"] == ""


@pytest.mark.asyncio
async def test_an_upload_without_a_name_is_treated_as_mp3(isolated, monkeypatch):
  monkeypatch.setattr(storage, "ensure_local_dirs", lambda: None)
  entry = await storage.save_upload(Upload(b"x", None), "t1", "")
  assert entry["stored_filename"] == "media.mp3" and entry["title"] == "media.mp3"


@pytest.mark.asyncio
async def test_unsupported_formats_are_refused_before_touching_the_disk(isolated):
  with pytest.raises(TranscriptionJobError) as raised:
    await storage.save_upload(Upload(b"x", "a.exe"), "t1", "")
  assert raised.value.code == "unsupported_format" and "Formato '.exe' no soportado" in raised.value.user_message
  assert not (isolated / "transcriptions" / "t1").exists()


@pytest.mark.asyncio
async def test_empty_uploads_are_refused_and_leave_nothing_behind(isolated, monkeypatch):
  monkeypatch.setattr(storage, "ensure_local_dirs", lambda: None)
  with pytest.raises(TranscriptionJobError) as raised:
    await storage.save_upload(Upload(b"", "a.mp3"), "t1", "")
  assert raised.value.code == "unsupported_format" and raised.value.user_message == "El archivo multimedia está vacío."
  assert not (isolated / "transcriptions" / "t1").exists()


@pytest.mark.asyncio
async def test_uploads_over_the_limit_are_refused_and_cleaned_up(isolated, monkeypatch):
  monkeypatch.setattr(storage, "ensure_local_dirs", lambda: None)
  monkeypatch.setattr(storage.config, "max_upload_bytes", lambda: 10)
  with pytest.raises(TranscriptionJobError) as raised:
    await storage.save_upload(Upload(b"x" * 11, "a.mp3"), "t1", "")
  assert raised.value.code == "file_too_large" and raised.value.user_message == "El archivo supera el máximo de 0 MB."
  assert not (isolated / "transcriptions" / "t1").exists()
  entry = await storage.save_upload(Upload(b"x" * 10, "a.mp3"), "t1", "")
  assert entry["size_bytes"] == 10


@pytest.mark.asyncio
async def test_a_failed_upload_keeps_a_folder_that_has_other_files(isolated, monkeypatch):
  monkeypatch.setattr(storage, "ensure_local_dirs", lambda: None)
  folder = _folder(isolated)
  (folder / "audio.wav").write_bytes(b"a")
  with pytest.raises(TranscriptionJobError):
    await storage.save_upload(Upload(b"", "a.mp3"), "t1", "")
  assert (folder / "audio.wav").exists() and not (folder / ".media.mp3.part").exists()


@pytest.mark.asyncio
async def test_the_size_limit_is_read_in_megabytes(isolated, monkeypatch):
  monkeypatch.setattr(storage, "ensure_local_dirs", lambda: None)
  monkeypatch.setenv("TRANSCRIPTION_MAX_UPLOAD_MB", "1")
  with pytest.raises(TranscriptionJobError) as raised:
    await storage.save_upload(Upload(b"x" * (1024 * 1024 + 1), "a.mp3"), "t1", "")
  assert raised.value.user_message == "El archivo supera el máximo de 1 MB."


# --- local files --------------------------------------------------------------------


def test_local_roots_match_by_directory_not_by_text_prefix(isolated, monkeypatch):
  root = isolated / "media"
  root.mkdir()
  (isolated / "media-other").mkdir()
  monkeypatch.setenv("TRANSCRIPTION_LOCAL_ROOTS", str(root))
  inside = root / "a.mp3"
  assert storage.match_local_root(inside) == (os.path.realpath(inside), os.path.realpath(root) + os.sep)
  assert storage.match_local_root(f"  '{inside}'  ") is not None
  assert storage.match_local_root(f'"{inside}"') is not None
  assert storage.match_local_root(isolated / "media-other" / "a.mp3") is None
  assert storage.match_local_root(root) is None
  assert storage.match_local_root("  ") is None and storage.match_local_root("''") is None
  assert storage.is_allowed_local_path(inside) is True and storage.is_allowed_local_path(isolated / "x") is False


def test_local_media_needs_desktop_mode_and_an_allowed_path(isolated, monkeypatch):
  root = isolated / "media"
  root.mkdir()
  source = root / "talk.mp3"
  source.write_bytes(b"data")
  monkeypatch.setenv("TRANSCRIPTION_LOCAL_ROOTS", str(root))
  assert _code(storage.local_media_entry, "t1", str(source), "T").user_message == "Ruta local no permitida."
  _desktop(monkeypatch, root)
  assert _code(storage.local_media_entry, "t1", str(isolated / "outside.mp3"), "T").user_message == "Ruta local no permitida."


def test_local_media_rechecks_the_prefix_next_to_the_file_access(isolated, monkeypatch):
  _desktop(monkeypatch, isolated)
  monkeypatch.setattr(storage, "match_local_root", lambda raw: ("/etc/passwd", "/safe/"))
  assert _code(storage.local_media_entry, "t1", "/etc/passwd", "T").user_message == "Ruta local no permitida."


def test_local_media_must_be_an_existing_supported_file(isolated, monkeypatch):
  root = isolated / "media"
  root.mkdir()
  _desktop(monkeypatch, root)
  missing = root / "none.mp3"
  error = _code(storage.local_media_entry, "t1", str(missing), "T")
  assert error.code == "bad_request" and error.user_message == f"El archivo local no existe o no es accesible: {missing}"
  (root / "notes.txt").write_bytes(b"x")
  assert _code(storage.local_media_entry, "t1", str(root / "notes.txt"), "T").code == "unsupported_format"
  (root / "empty.mp3").write_bytes(b"")
  assert _code(storage.local_media_entry, "t1", str(root / "empty.mp3"), "T").user_message == "El archivo está vacío."
  assert _code(storage.local_media_entry, "t1", str(root), "T").code == "bad_request"


def test_local_media_is_referenced_without_copying_it(isolated, monkeypatch):
  root = isolated / "media"
  root.mkdir()
  source = root / "talk.mp4"
  source.write_bytes(b"data")
  _desktop(monkeypatch, root)
  entry = storage.local_media_entry("t1", str(source), " Charla ", " d ")
  real = str(source.resolve())
  assert (entry["path"], entry["source_path"], entry["filename"], entry["stored_filename"]) == (real, real, "talk.mp4", "talk.mp4")
  assert (entry["size_bytes"], entry["hash"], entry["is_video"], entry["title"], entry["description"]) == (4, "", True, "Charla", "d")
  assert (isolated / "transcriptions" / "t1").is_dir()
  assert storage.local_media_entry("t1", str(source), "", "")["title"] == "talk.mp4"


# --- records and cleanup ------------------------------------------------------------


def test_the_initial_record_keeps_the_entry_and_the_source_path():
  entry = {"id": "t1", "title": "T", "description": "d", "size_bytes": 5, "file_size_formatted": "5 B", "original_filename": "a.mp3",
           "stored_filename": "media.mp3", "path": "/p", "created_at": "now"}
  record = storage.initial_record(entry, "u1")
  assert record["metadata"] == {"title": "T", "description": "d", "size_bytes": 5, "file_size_formatted": "5 B"}
  assert (record["id"], record["media_id"], record["user_id"], record["status"], record["source"]) == ("t1", "t1", "u1", "uploaded", "cloud")
  assert (record["language"], record["duration_seconds"], record["segments"], record["summary"], record["summary_status"]) == ("es", 0.0, [], None, "skipped")
  assert record["media"] is entry and record["path"] == "/p" and record["created_at"] == "now"
  with_source = storage.initial_record({**entry, "source_path": "/src"}, None)
  assert with_source["metadata"]["source_path"] == "/src" and with_source["user_id"] is None
  minimal = storage.initial_record({"id": "t2", "title": "T", "original_filename": "a", "stored_filename": "b", "path": "p", "created_at": "c"}, None)
  assert minimal["metadata"] == {"title": "T", "description": "", "size_bytes": 0, "file_size_formatted": None}


def test_the_original_is_removed_only_once_the_wav_exists(isolated):
  folder = _folder(isolated)
  (folder / "media.mp4").write_bytes(b"v")
  storage.remove_original_after_extraction("t1")
  assert (folder / "media.mp4").exists()
  (folder / "audio.wav").write_bytes(b"a")
  storage.remove_original_after_extraction("t1")
  assert not (folder / "media.mp4").exists() and (folder / "audio.wav").exists()


def test_a_media_file_that_cannot_be_removed_is_only_logged(isolated, monkeypatch, caplog):
  folder = _folder(isolated)
  (folder / "audio.wav").write_bytes(b"a")
  (folder / "media.mp4").write_bytes(b"v")
  original = type(folder).unlink

  def failing(self, *args, **kwargs):
    raise OSError("locked")

  monkeypatch.setattr(type(folder), "unlink", failing)
  with caplog.at_level(logging.WARNING):
    storage.remove_original_after_extraction("t1")
  monkeypatch.setattr(type(folder), "unlink", original)
  assert any("Could not delete original media" in r.getMessage() and "locked" in r.getMessage() for r in caplog.records)


def test_deleting_a_folder_or_its_chunks(isolated):
  folder = _folder(isolated)
  (folder / "chunks").mkdir()
  (folder / "chunks" / "chunk_000.mp3").write_bytes(b"c")
  (folder / "audio.wav").write_bytes(b"a")
  storage.delete_chunks("t1")
  assert not (folder / "chunks").exists() and (folder / "audio.wav").exists()
  storage.delete_chunks("t1")
  storage.delete_folder("t1")
  assert not folder.exists()
  storage.delete_folder("t1")
  (isolated / "transcriptions" / "file").write_bytes(b"x")
  storage.delete_folder("file")
  assert (isolated / "transcriptions" / "file").exists()

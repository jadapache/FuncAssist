from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

from app.core.settings import WHISPER_MODELS_DIR

def get_whisper_cache_dir() -> Path:
  WHISPER_MODELS_DIR.mkdir(parents=True, exist_ok=True)
  return WHISPER_MODELS_DIR


def get_local_models_info() -> List[Dict[str, Any]]:
  """Inspects the local cache directory to list all local transcription models and their download status."""
  from app.ai.builtin_local import load_builtin_catalog

  cache_dir = get_whisper_cache_dir()
  results: List[Dict[str, Any]] = []

  try:
    catalog_models = load_builtin_catalog(task_type="transcription")
  except Exception:
    catalog_models = {}

  if catalog_models:
    for model_id, m in catalog_models.items():
      provider = m.get("provider", "builtin")
      clean_id = model_id.replace("whisper-", "")

      if provider == "onnx" or "parakeet" in model_id or "sense-voice" in model_id or "onnx" in model_id:
        o_dir = cache_dir / f"onnx-{model_id}"
        onnx_files = list(o_dir.glob("*.onnx")) if o_dir.exists() else []
        is_downloaded = len(onnx_files) > 0 and sum(f.stat().st_size for f in onnx_files) > 1024 * 1024
        disk_size_mb = round(sum(f.stat().st_size for f in onnx_files) / (1024 * 1024), 1) if is_downloaded else 0.0
        file_path = str(o_dir) if is_downloaded else None
      elif provider == "faster-whisper" or model_id.startswith("fw-"):
        fw_size = model_id.replace("fw-", "").replace("faster-whisper-", "")
        fw_dir = cache_dir / f"faster-whisper-{fw_size}"
        model_bin = fw_dir / "model.bin"
        is_downloaded = model_bin.exists() and model_bin.stat().st_size > 1024 * 1024
        disk_size_mb = round(model_bin.stat().st_size / (1024 * 1024), 1) if is_downloaded else 0.0
        file_path = str(fw_dir) if is_downloaded else None
      elif provider == "moonshine" or model_id.startswith("moonshine"):
        m_dir = cache_dir / model_id
        is_downloaded = m_dir.exists() and any(m_dir.iterdir()) if m_dir.exists() else False
        disk_size_mb = 90.0 if (is_downloaded and "tiny" in model_id) else (360.0 if is_downloaded else 0.0)
        file_path = str(m_dir) if is_downloaded else None
      else:
        model_file = cache_dir / f"{clean_id}.pt"
        is_downloaded = model_file.exists() and model_file.stat().st_size > 1024 * 1024
        disk_size_mb = round(model_file.stat().st_size / (1024 * 1024), 1) if is_downloaded else 0.0
        file_path = str(model_file) if is_downloaded else None

      results.append({
        "id": model_id,
        "name": m.get("name", f"Whisper {model_id.title()}"),
        "size": m.get("size", "142 MB"),
        "accuracy": m.get("accuracy", "Estándar"),
        "description": m.get("description", ""),
        "provider": provider,
        "engine": m.get("engine", "openai-whisper"),
        "is_downloaded": is_downloaded,
        "disk_size_mb": disk_size_mb,
        "file_path": file_path,
      })
    return results

  for model_id in ("tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"):
    model_file = cache_dir / f"{model_id}.pt"
    is_downloaded = model_file.exists() and model_file.stat().st_size > 1024 * 1024
    disk_size_mb = round(model_file.stat().st_size / (1024 * 1024), 1) if is_downloaded else 0.0
    results.append({
      "id": model_id,
      "name": f"Whisper {model_id.title()}",
      "size": "N/A",
      "accuracy": "N/A",
      "description": "Modelo Whisper local",
      "is_downloaded": is_downloaded,
      "disk_size_mb": disk_size_mb,
      "file_path": str(model_file) if is_downloaded else None,
    })
  return results


# Track active Whisper downloads and cancellation tokens
_WHISPER_DOWNLOADS: Dict[str, Dict[str, Any]] = {}
_WHISPER_CANCEL_EVENTS: Dict[str, threading.Event] = {}
_WHISPER_LOCK = threading.Lock()


def get_active_whisper_downloads() -> List[Dict[str, Any]]:
  """Returns active Whisper download tasks and purges finished tasks after 5 seconds."""
  now = time.time()
  with _WHISPER_LOCK:
    to_purge = [
      cid for cid, task in _WHISPER_DOWNLOADS.items()
      if task.get("status") in ("complete", "cancelled", "failed")
      and (now - task.get("finished_at", 0) > 5.0)
    ]
    for cid in to_purge:
      _WHISPER_DOWNLOADS.pop(cid, None)
      _WHISPER_CANCEL_EVENTS.pop(cid, None)
    return list(_WHISPER_DOWNLOADS.values())


def prepare_whisper_download(model_id: str) -> str:
  """Synchronously initializes Whisper download tracking to 0% before background thread starts."""
  from app.ai.builtin_local import load_builtin_catalog
  catalog = load_builtin_catalog(task_type="transcription")
  clean_id = model_id.replace("whisper-", "").strip().lower()
  meta = catalog.get(model_id) or catalog.get(clean_id) or catalog.get(f"whisper-{clean_id}")
  name = meta.get("name") if meta else f"Whisper {clean_id.title()}"
  with _WHISPER_LOCK:
    _WHISPER_CANCEL_EVENTS.pop(clean_id, None)
    _WHISPER_DOWNLOADS[clean_id] = {
      "id": clean_id,
      "title": f"Descargando {name}",
      "type": "download",
      "progress": 0,
      "status": "downloading",
      "stageText": "Conectando con el repositorio...",
      "speedOrSize": "0 MB",
      "eta": None,
    }
  return clean_id


def cancel_whisper_download(model_id: str) -> bool:
  """Cancels an active Whisper model download and removes partial download files."""
  clean = model_id.replace("whisper-", "").strip().lower()
  with _WHISPER_LOCK:
    event = _WHISPER_CANCEL_EVENTS.get(clean)
    if event:
      event.set()
      if clean in _WHISPER_DOWNLOADS:
        _WHISPER_DOWNLOADS[clean]["status"] = "cancelled"
        _WHISPER_DOWNLOADS[clean]["progress"] = 0
        _WHISPER_DOWNLOADS[clean]["stageText"] = "Descarga cancelada por el usuario"
        _WHISPER_DOWNLOADS[clean]["finished_at"] = time.time()
      logger.info(f"Cancellation requested for Whisper model {clean}")

      cache_dir = get_whisper_cache_dir()
      tmp_file = cache_dir / f"{clean}.pt.download"
      if tmp_file.exists():
        try:
          tmp_file.unlink()
          logger.info(f"Removed partial Whisper download file: {tmp_file}")
        except Exception:
          pass
      return True
  return False


def _make_hf_progress_tqdm(canonical_id: str, cancel_event: threading.Event):
  """Create a custom tqdm class that updates _WHISPER_DOWNLOADS during snapshot_download."""
  from tqdm.auto import tqdm
  start_time = time.time()
  last_update = [0.0]

  class _HFTqdm(tqdm):
    def update(self, n=1):
      super().update(n)
      if cancel_event.is_set():
        raise RuntimeError("Descarga cancelada por el usuario.")
      now = time.time()
      if now - last_update[0] >= 0.2:
        last_update[0] = now
        downloaded = self.n
        total_size = self.total or 0
        elapsed = max(0.1, now - start_time)
        speed_mb = (downloaded / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0
        speed_str = f"{speed_mb:.1f} MB/s" if speed_mb > 0 else ""

        pct = round((downloaded / total_size) * 100, 1) if total_size > 0 else 0.0
        dl_mb = round(downloaded / (1024 * 1024), 1)
        tot_mb = round(total_size / (1024 * 1024), 1) if total_size > 0 else 0.0

        eta_str = None
        if speed_mb > 0 and total_size > downloaded:
          eta_sec = int((total_size - downloaded) / (speed_mb * 1024 * 1024))
          eta_str = f"{eta_sec // 60}m {eta_sec % 60}s" if eta_sec >= 60 else f"{eta_sec}s"

        with _WHISPER_LOCK:
          if canonical_id in _WHISPER_DOWNLOADS:
            _WHISPER_DOWNLOADS[canonical_id].update({
              "progress": int(pct),
              "stageText": f"{dl_mb} MB de {tot_mb} MB ({speed_str})" if tot_mb > 0 else f"{dl_mb} MB ({speed_str})",
              "speedOrSize": f"{dl_mb}/{tot_mb} MB" if tot_mb > 0 else f"{dl_mb} MB",
              "eta": eta_str,
            })

  return _HFTqdm


def download_model_file(
  model_id: str,
  progress_callback: Optional[Callable[[int, int, float], None]] = None,
) -> Path:
  """Downloads a local transcription model file (.pt for whisper, directory for faster-whisper/moonshine/onnx)."""
  clean_id = model_id.replace("whisper-", "").strip().lower()
  cancel_event = threading.Event()

  with _WHISPER_LOCK:
    _WHISPER_CANCEL_EVENTS[clean_id] = cancel_event
    if clean_id in _WHISPER_DOWNLOADS:
      _WHISPER_DOWNLOADS[clean_id]["status"] = "downloading"

  try:
    # 0. ONNX Models (Parakeet, SenseVoice, Moonshine ONNX, Whisper ONNX)
    if "parakeet" in model_id or "sense-voice" in model_id or "onnx" in model_id:
      from app.features.transcription.providers.onnx_provider import OnnxTranscriptionProvider
      op = OnnxTranscriptionProvider()
      repo = op.HF_REPOS.get(clean_id, op.HF_REPOS.get(model_id, f"csukuangfj/{model_id}"))
      target_dir = op._model_dir(model_id)
      if op.is_model_downloaded(model_id):
        return target_dir

      try:
        from huggingface_hub import snapshot_download
        target_dir.mkdir(parents=True, exist_ok=True)
        tqdm_cls = _make_hf_progress_tqdm(clean_id, cancel_event)
        snapshot_download(repo_id=repo, local_dir=str(target_dir), tqdm_class=tqdm_cls)

        with _WHISPER_LOCK:
          if clean_id in _WHISPER_DOWNLOADS:
            _WHISPER_DOWNLOADS[clean_id].update({
              "progress": 100,
              "status": "complete",
              "stageText": "Descarga completada con éxito",
              "speedOrSize": "Listo",
              "eta": None,
              "finished_at": time.time(),
            })
        return target_dir
      except Exception as exc:
        raise RuntimeError(f"Error descargando modelo ONNX {model_id} desde {repo}: {exc}") from exc

    # 1. Faster Whisper models
    if model_id.startswith("fw-") or "faster-whisper" in model_id:
      from app.features.transcription.providers.faster_whisper import FasterWhisperProvider
      fw = FasterWhisperProvider()
      clean = fw._clean_model_id(model_id)
      repo = fw.HF_REPOS.get(clean, f"Systran/faster-whisper-{clean}")
      target_dir = fw._model_dir(clean)
      if (target_dir / "model.bin").exists():
        return target_dir

      try:
        from huggingface_hub import snapshot_download
        target_dir.mkdir(parents=True, exist_ok=True)
        tqdm_cls = _make_hf_progress_tqdm(clean_id, cancel_event)
        snapshot_download(repo_id=repo, local_dir=str(target_dir), tqdm_class=tqdm_cls)

        with _WHISPER_LOCK:
          if clean_id in _WHISPER_DOWNLOADS:
            _WHISPER_DOWNLOADS[clean_id].update({
              "progress": 100,
              "status": "complete",
              "stageText": "Descarga completada con éxito",
              "speedOrSize": "Listo",
              "eta": None,
              "finished_at": time.time(),
            })
        return target_dir
      except Exception as exc:
        raise RuntimeError(f"Error descargando modelo Faster Whisper {model_id} desde {repo}: {exc}") from exc

    # 2. Moonshine models
    if model_id.startswith("moonshine"):
      from app.features.transcription.providers.moonshine import MoonshineProvider
      mp = MoonshineProvider()
      clean = mp._clean_model_id(model_id)
      repo = mp.MODELS.get(clean, "UsefulSensors/moonshine-tiny")
      target_dir = get_whisper_cache_dir() / clean
      if target_dir.exists() and any(target_dir.iterdir()):
        return target_dir

      try:
        from huggingface_hub import snapshot_download
        target_dir.mkdir(parents=True, exist_ok=True)
        tqdm_cls = _make_hf_progress_tqdm(clean_id, cancel_event)
        snapshot_download(repo_id=repo, local_dir=str(target_dir), tqdm_class=tqdm_cls)

        with _WHISPER_LOCK:
          if clean_id in _WHISPER_DOWNLOADS:
            _WHISPER_DOWNLOADS[clean_id].update({
              "progress": 100,
              "status": "complete",
              "stageText": "Descarga completada con éxito",
              "speedOrSize": "Listo",
              "eta": None,
              "finished_at": time.time(),
            })
        return target_dir
      except Exception as exc:
        raise RuntimeError(f"Error descargando modelo Moonshine {model_id} desde {repo}: {exc}") from exc

    # 3. OpenAI Whisper models (.pt)
    import whisper

    if clean_id not in whisper._MODELS:
      raise ValueError(f"Modelo Whisper desconocido: {clean_id}. Modelos disponibles: {list(whisper._MODELS.keys())}")

    url = whisper._MODELS[clean_id]
    cache_dir = get_whisper_cache_dir()
    target_file = cache_dir / f"{clean_id}.pt"
    tmp_file = cache_dir / f"{clean_id}.pt.download"

    if target_file.exists() and target_file.stat().st_size > 1024 * 1024:
      logger.info(f"Whisper model {clean_id} already exists at {target_file}")
      return target_file

    if tmp_file.exists():
      try:
        tmp_file.unlink()
      except Exception:
        pass

    start_time = time.time()
    last_update_time = 0.0

    logger.info(f"Downloading Whisper model {clean_id} from {url} to {target_file}")

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; QA-Project-MGMT/1.0)"})
    with urllib.request.urlopen(req) as response:
      total_size = int(response.headers.get("content-length", 0))
      downloaded = 0
      chunk_size = 1024 * 512  # 512 KB chunks

      with open(tmp_file, "wb") as f_out:
        while True:
          if cancel_event.is_set():
            logger.warning(f"Whisper download cancelled for {clean_id}")
            raise RuntimeError(f"Descarga de Whisper {clean_id} cancelada por el usuario.")

          chunk = response.read(chunk_size)
          if not chunk:
            break
          f_out.write(chunk)
          downloaded += len(chunk)

          now = time.time()
          if now - last_update_time >= 0.2:
            last_update_time = now
            elapsed = max(0.1, now - start_time)
            speed_mb = (downloaded / (1024 * 1024)) / elapsed
            speed_str = f"{speed_mb:.1f} MB/s"
            pct = round((downloaded / total_size) * 100, 1) if total_size > 0 else 0.0
            dl_mb = round(downloaded / (1024 * 1024), 1)
            tot_mb = round(total_size / (1024 * 1024), 1) if total_size > 0 else 0.0

            eta_str = None
            if speed_mb > 0 and total_size > downloaded:
              eta_sec = int((total_size - downloaded) / (speed_mb * 1024 * 1024))
              eta_str = f"{eta_sec // 60}m {eta_sec % 60}s" if eta_sec >= 60 else f"{eta_sec}s"

            with _WHISPER_LOCK:
              if clean_id in _WHISPER_DOWNLOADS:
                _WHISPER_DOWNLOADS[clean_id].update({
                  "progress": int(pct),
                  "stageText": f"{dl_mb} MB de {tot_mb} MB ({speed_str})",
                  "speedOrSize": f"{dl_mb}/{tot_mb} MB",
                  "eta": eta_str,
                })

            if progress_callback:
              progress_callback(downloaded, total_size, pct)

    # Atomically replace
    if target_file.exists():
      target_file.unlink()
    tmp_file.rename(target_file)

    with _WHISPER_LOCK:
      if clean_id in _WHISPER_DOWNLOADS:
        _WHISPER_DOWNLOADS[clean_id].update({
          "progress": 100,
          "status": "complete",
          "stageText": "Descarga completada con éxito",
          "speedOrSize": "Listo",
          "eta": None,
          "finished_at": time.time(),
        })

    logger.info(f"Whisper model {clean_id} downloaded successfully to {target_file}")
    return target_file

  except Exception as exc:
    tmp_file_check = cache_dir / f"{clean_id}.pt.download" if 'cache_dir' in locals() else None
    if tmp_file_check and tmp_file_check.exists():
      try:
        tmp_file_check.unlink()
      except Exception:
        pass

    with _WHISPER_LOCK:
      if clean_id in _WHISPER_DOWNLOADS:
        is_cancel = cancel_event.is_set() or "cancelada" in str(exc).lower()
        _WHISPER_DOWNLOADS[clean_id].update({
          "status": "cancelled" if is_cancel else "failed",
          "stageText": "Descarga cancelada" if is_cancel else f"Error: {exc}",
          "finished_at": time.time(),
        })
    raise
  finally:
    with _WHISPER_LOCK:
      _WHISPER_CANCEL_EVENTS.pop(clean_id, None)


def delete_model_file(model_id: str) -> bool:
  """Deletes a downloaded local transcription model file or directory from the cache directory."""
  cache_dir = get_whisper_cache_dir()
  clean = model_id.strip().lower()
  clean_fw = clean.replace("fw-", "").replace("faster-whisper-", "")
  
  target_file = cache_dir / f"{clean}.pt"
  tmp_file = cache_dir / f"{clean}.pt.download"
  fw_dir = cache_dir / f"faster-whisper-{clean_fw}"
  m_dir = cache_dir / clean
  onnx_dir = cache_dir / f"onnx-{clean}"

  deleted = False
  if onnx_dir.exists() and onnx_dir.is_dir():
    try:
      shutil.rmtree(onnx_dir, ignore_errors=True)
      deleted = True
      logger.info(f"Deleted ONNX model dir: {onnx_dir}")
    except Exception as exc:
      logger.error(f"Error deleting model directory {onnx_dir}: {exc}")
      raise

  if target_file.exists():
    try:
      target_file.unlink()
      deleted = True
      logger.info(f"Deleted Whisper model file: {target_file}")
    except Exception as exc:
      logger.error(f"Error deleting model file {target_file}: {exc}")
      raise

  if fw_dir.exists() and fw_dir.is_dir():
    try:
      shutil.rmtree(fw_dir, ignore_errors=True)
      deleted = True
      logger.info(f"Deleted faster-whisper model dir: {fw_dir}")
    except Exception as exc:
      logger.error(f"Error deleting model directory {fw_dir}: {exc}")
      raise

  if m_dir.exists() and m_dir.is_dir():
    try:
      shutil.rmtree(m_dir, ignore_errors=True)
      deleted = True
      logger.info(f"Deleted moonshine model dir: {m_dir}")
    except Exception as exc:
      logger.error(f"Error deleting model directory {m_dir}: {exc}")
      raise

  if tmp_file.exists():
    try:
      tmp_file.unlink()
    except Exception:
      pass

  with _WHISPER_LOCK:
    _WHISPER_DOWNLOADS.pop(model_id, None)
    _WHISPER_DOWNLOADS.pop(clean, None)

  return deleted


class ProgressInterceptorTqdm:
  """Intercepts tqdm updates from Whisper to provide real-time frame progress callbacks and cancellation checks."""

  def __init__(
    self,
    *args,
    on_progress: Optional[Callable[[int, str, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    **kwargs,
  ):
    self.total = kwargs.get("total") or 1
    self.n = kwargs.get("initial", 0)
    self.on_progress = on_progress
    self.cancel_check = cancel_check
    self.start_time = time.time()
    self.last_emit_time = 0.0

  def update(self, n: int = 1):
    self.n += n
    if self.cancel_check and self.cancel_check():
      raise RuntimeError("Transcripción cancelada por el usuario.")

    now = time.time()
    # Throttle callbacks to at most once every 0.4s to avoid excessive events
    if (now - self.last_emit_time) >= 0.4 or self.n >= self.total:
      self.last_emit_time = now
      fraction = min(1.0, max(0.0, float(self.n) / float(self.total)))
      prog_pct = int(20 + fraction * 55)  # Range: 20% to 75%
      
      elapsed = now - self.start_time
      if fraction > 0:
        remaining = max(1.0, (elapsed / fraction) - elapsed)
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        eta_str = f"~{mins} min {secs} s" if mins > 0 else f"~{secs} s"
      else:
        eta_str = "~30 s"

      pct_display = int(fraction * 100)
      message = f"Decodificando audio ({pct_display}% procesado)..."
      if self.on_progress:
        try:
          self.on_progress(prog_pct, message, eta_str)
        except Exception as exc:
          logger.debug(f"Progress callback error: {exc}")

  def close(self):
    pass

  def __enter__(self):
    return self

  def __exit__(self, *args):
    self.close()


class WhisperLocalService:
  def __init__(self, model_size: str = "base"):
    self.model_size = model_size
    self._model = None

  def _get_model(self):
    if self._model is None:
      try:
        import whisper
        cache_dir = get_whisper_cache_dir()
        logger.info(f"Loading local Whisper model: {self.model_size} from {cache_dir}")
        self._model = whisper.load_model(self.model_size, download_root=str(cache_dir))
      except ImportError:
        raise RuntimeError(
          "El paquete 'openai-whisper' no está instalado en el entorno local de Python. "
          "Para utilizar transcripción local, instala 'openai-whisper' y 'ffmpeg', o usa el modo Cloud (Groq / OpenAI)."
        )
      except Exception as exc:
        raise RuntimeError(f"Error al cargar el modelo local Whisper ({self.model_size}): {exc}") from exc
    return self._model

  def is_available(self) -> bool:
    try:
      import whisper  # noqa: F401
      return True
    except ImportError:
      return False

  def transcribe(
    self,
    audio_path: Path,
    language: Optional[str] = None,
    task: str = "transcribe",
    on_progress: Optional[Callable[[int, str, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
  ) -> Dict[str, Any]:
    import tqdm
    model = self._get_model()
    audio_file = str(audio_path)

    options: Dict[str, Any] = {"task": task, "verbose": False}
    if language:
      options["language"] = language

    # Intercept tqdm within whisper to stream real-time progression and check cancellation
    orig_tqdm = tqdm.tqdm

    def custom_tqdm_factory(*args, **kwargs):
      return ProgressInterceptorTqdm(
        *args,
        on_progress=on_progress,
        cancel_check=cancel_check,
        **kwargs,
      )

    tqdm.tqdm = custom_tqdm_factory
    try:
      result = model.transcribe(audio_file, **options)
    except Exception as exc:
      if "cancelada por el usuario" in str(exc).lower():
        raise
      raise RuntimeError(f"Error durante la transcripción local con Whisper: {exc}") from exc
    finally:
      tqdm.tqdm = orig_tqdm

    detected_lang = result.get("language", language or "es")
    raw_segments = result.get("segments", [])
    formatted_segments: List[Dict[str, Any]] = []

    for idx, seg in enumerate(raw_segments):
      formatted_segments.append({
        "start": float(seg.get("start", 0.0)),
        "end": float(seg.get("end", 0.0)),
        "text": seg.get("text", "").strip(),
        "speaker": f"Participante {(idx % 2) + 1}",
      })

    full_text = result.get("text", "").strip()

    return {
      "language": detected_lang,
      "text": full_text,
      "segments": formatted_segments,
      "duration": formatted_segments[-1]["end"] if formatted_segments else 0.0,
    }


def extract_audio_track(media_path: Path, output_wav_path: Path) -> Path:
  """
  Extract audio from a video or non-WAV audio file and convert to 16 kHz mono PCM WAV.
  Returns output_wav_path if converted, or media_path if already .wav or ffmpeg is unavailable.
  """
  suffix = media_path.suffix.lower()
  if suffix == ".wav":
    return media_path

  ffmpeg_cmd = shutil.which("ffmpeg")
  if not ffmpeg_cmd:
    return media_path

  try:
    cmd = [
      ffmpeg_cmd,
      "-y",
      "-i", str(media_path),
      "-vn",                  # strip video stream
      "-acodec", "pcm_s16le", # 16-bit PCM — native Whisper input
      "-ar", "16000",         # 16 kHz — Whisper's required sample rate
      "-ac", "1",             # mono
      str(output_wav_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if output_wav_path.exists() and output_wav_path.stat().st_size > 0:
      return output_wav_path
  except Exception as e:
    logger.warning(f"FFmpeg conversion failed: {e}, using original media file.")

  return media_path

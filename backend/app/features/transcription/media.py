"""Async ffmpeg/ffprobe helpers for the transcription pipeline.

Every call runs as a cancellable subprocess (cancelling the awaiting task kills the process), so a
long extraction never blocks the event loop and a cancelled job stops ffmpeg immediately.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import shutil
from pathlib import Path
from typing import Callable, Optional, Sequence

from app.core.exceptions import AudioAnalysisError, FFmpegError
from app.features.transcription.ffmpeg_utils import ensure_ffmpeg_available, get_ffmpeg_binary

logger = logging.getLogger(__name__)
# Noise floor -> silencedetect threshold: floor + margin, clamped to a sane speech range.
SILENCE_MARGIN_DB = 6.0
SILENCE_THRESHOLD_MIN_DB = -50.0
SILENCE_THRESHOLD_MAX_DB = -25.0
SPEECH_PADDING_S = 0.3


def find_ffprobe() -> Optional[str]:
  found = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
  if found:
    return found
  ffmpeg = get_ffmpeg_binary()
  if ffmpeg:
    sibling = Path(ffmpeg).with_name(Path(ffmpeg).name.replace("ffmpeg", "ffprobe"))
    if sibling.is_file():
      return str(sibling)
  return None


async def run_process(
  args: Sequence[str],
  *,
  timeout: float,
  on_stdout_line: Optional[Callable[[str], None]] = None,
) -> tuple[int, str, str]:
  """Run a subprocess; kill it on timeout or cancellation. Returns (returncode, stdout, stderr)."""
  proc = await asyncio.create_subprocess_exec(
    *args,
    stdin=asyncio.subprocess.DEVNULL,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
  )
  stdout_lines: list[str] = []

  async def _read_stdout() -> None:
    assert proc.stdout is not None
    while True:
      raw = await proc.stdout.readline()
      if not raw:
        break
      line = raw.decode("utf-8", errors="replace").rstrip()
      if on_stdout_line:
        on_stdout_line(line)
      else:
        stdout_lines.append(line)

  async def _read_stderr() -> bytes:
    assert proc.stderr is not None
    return await proc.stderr.read()

  try:
    _, stderr_bytes = await asyncio.wait_for(
      asyncio.gather(_read_stdout(), _read_stderr()), timeout=timeout
    )
    returncode = await proc.wait()
  except (asyncio.TimeoutError, asyncio.CancelledError):
    _kill(proc)
    raise
  return returncode, "\n".join(stdout_lines), stderr_bytes.decode("utf-8", errors="replace")


def _kill(proc: asyncio.subprocess.Process) -> None:
  if proc.returncode is None:
    try:
      proc.kill()
    except ProcessLookupError:
      pass


async def probe_duration(path: Path) -> float:
  """Container duration in seconds (ffprobe). Raises AudioAnalysisError when unreadable."""
  if not path.exists():
    raise AudioAnalysisError("File not found", filename=path.name)
  ffprobe = find_ffprobe()
  if not ffprobe:
    raise AudioAnalysisError("ffprobe not found in PATH", filename=path.name)
  try:
    code, out, err = await run_process(
      [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type",
       "-of", "default=noprint_wrappers=1", str(path)],
      timeout=60,
    )
  except asyncio.TimeoutError as exc:
    raise AudioAnalysisError("ffprobe timeout (file may be corrupted)", filename=path.name) from exc
  if code != 0:
    raise AudioAnalysisError(f"ffprobe failed: {err.strip()[:300]}", filename=path.name)
  if "codec_type=audio" not in out:
    raise AudioAnalysisError("The file has no audio stream", filename=path.name)
  match = re.search(r"duration=([0-9.]+)", out)
  duration = float(match.group(1)) if match else 0.0
  if duration <= 0:
    raise AudioAnalysisError("Duration is zero or could not be read", filename=path.name)
  return duration


def _parse_progress_seconds(line: str) -> Optional[float]:
  # `-progress pipe:1` prints out_time_us / out_time_ms (both microseconds) and out_time=HH:MM:SS.us
  if line.startswith(("out_time_us=", "out_time_ms=")):
    try:
      return int(line.split("=", 1)[1]) / 1_000_000
    except ValueError:
      return None
  return None


async def extract_audio(
  source: Path,
  dest_wav: Path,
  duration_s: float,
  on_progress: Optional[Callable[[float], None]] = None,
) -> Path:
  """Decode any media to 16 kHz mono PCM WAV, reporting progress as a 0..1 fraction."""
  ffmpeg = ensure_ffmpeg_available()
  dest_wav.parent.mkdir(parents=True, exist_ok=True)
  tmp = dest_wav.with_suffix(".tmp.wav")

  def _line(line: str) -> None:
    seconds = _parse_progress_seconds(line)
    if seconds is not None and on_progress and duration_s > 0:
      on_progress(min(1.0, seconds / duration_s))

  timeout = max(300.0, duration_s * 0.5)
  code, _, err = await run_process(
    [ffmpeg, "-y", "-nostdin", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
     "-c:a", "pcm_s16le", "-progress", "pipe:1", "-nostats", "-loglevel", "error", str(tmp)],
    timeout=timeout,
    on_stdout_line=_line,
  )
  if code != 0 or not tmp.exists() or tmp.stat().st_size < 100:
    tmp.unlink(missing_ok=True)
    raise FFmpegError("FFmpeg audio extraction failed", stderr=err[-2000:], returncode=code)
  tmp.replace(dest_wav)
  return dest_wav


async def measure_noise_floor(wav: Path) -> Optional[float]:
  """Background noise level in dBFS: 10th percentile of per-second RMS levels (None if unknown)."""
  ffmpeg = ensure_ffmpeg_available()
  levels: list[float] = []

  def _line(line: str) -> None:
    if "RMS_level=" in line:
      try:
        value = float(line.split("=", 1)[1])
      except ValueError:
        return
      if math.isfinite(value):
        levels.append(value)

  try:
    await run_process(
      [ffmpeg, "-nostdin", "-i", str(wav), "-af",
       "asetnsamples=n=16000:p=0,astats=metadata=1:reset=1,"
       "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
       "-f", "null", "-"],
      timeout=600,
      on_stdout_line=_line,
    )
  except asyncio.TimeoutError:
    logger.warning("Noise floor measurement timed out for %s", wav.name)
    return None
  if not levels:
    return None
  levels.sort()
  return levels[max(0, int(len(levels) * 0.10) - 1)]


def silence_threshold_db(noise_floor_db: Optional[float]) -> float:
  if noise_floor_db is None:
    return -35.0
  return max(SILENCE_THRESHOLD_MIN_DB, min(SILENCE_THRESHOLD_MAX_DB, noise_floor_db + SILENCE_MARGIN_DB))


_SILENCE_START = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")


def parse_silencedetect(stderr: str, duration_s: float) -> list[tuple[float, float]]:
  silences: list[tuple[float, float]] = []
  start: Optional[float] = None
  for line in stderr.splitlines():
    m_start = _SILENCE_START.search(line)
    if m_start:
      start = max(0.0, float(m_start.group(1)))
      continue
    m_end = _SILENCE_END.search(line)
    if m_end and start is not None:
      silences.append((start, min(duration_s, float(m_end.group(1)))))
      start = None
  if start is not None and start < duration_s:
    silences.append((start, duration_s))
  return silences


async def detect_silences(wav: Path, threshold_db: float, min_silence_s: float, duration_s: float) -> list[tuple[float, float]]:
  ffmpeg = ensure_ffmpeg_available()
  code, _, err = await run_process(
    [ffmpeg, "-nostdin", "-i", str(wav), "-af",
     f"silencedetect=noise={threshold_db:.1f}dB:d={min_silence_s:.2f}", "-f", "null", "-"],
    timeout=600,
  )
  if code != 0:
    raise FFmpegError("FFmpeg silence detection failed", stderr=err[-2000:], returncode=code)
  return parse_silencedetect(err, duration_s)


async def export_regions(wav: Path, regions: Sequence[tuple[float, float]], dest_mp3: Path) -> Path:
  """Concatenate the given (start, end) regions of `wav` into one compact MP3 (sample-accurate)."""
  ffmpeg = ensure_ffmpeg_available()
  dest_mp3.parent.mkdir(parents=True, exist_ok=True)
  if not regions:
    raise FFmpegError("No audio regions to export")

  parts = [
    f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[r{i}]"
    for i, (start, end) in enumerate(regions)
  ]
  inputs = "".join(f"[r{i}]" for i in range(len(regions)))
  graph = ";\n".join(parts) + f";\n{inputs}concat=n={len(regions)}:v=0:a=1[out]"
  script = dest_mp3.with_suffix(".filter.txt")
  script.write_text(graph, encoding="utf-8")
  tmp = dest_mp3.with_suffix(".tmp.mp3")
  try:
    code, _, err = await run_process(
      [ffmpeg, "-y", "-nostdin", "-i", str(wav), "-filter_complex_script", str(script),
       "-map", "[out]", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "48k",
       "-loglevel", "error", str(tmp)],
      timeout=900,
    )
  finally:
    script.unlink(missing_ok=True)
  if code != 0 or not tmp.exists() or tmp.stat().st_size == 0:
    tmp.unlink(missing_ok=True)
    raise FFmpegError("FFmpeg chunk export failed", stderr=err[-2000:], returncode=code)
  tmp.replace(dest_mp3)
  return dest_mp3


async def export_clip(wav: Path, start: float, end: float, dest_mp3: Path) -> Path:
  return await export_regions(wav, [(start, end)], dest_mp3)

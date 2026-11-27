import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Tuple

from app.core.settings import BIN_DIR
from app.core.exceptions import FFmpegError

logger = logging.getLogger(__name__)

_CACHED_FFMPEG_PATH: str | None = None
_MIN_BUNDLED_BINARY_BYTES = 10000
_CONVERSION_TIMEOUT_S = 1800
_PROBE_TIMEOUT_S = 10
_SUSPICIOUSLY_SMALL_BYTES = 1000


def _ensure_in_path(directory: Path) -> None:
    dir_str = str(directory)
    current_path = os.environ.get("PATH", "")
    paths = current_path.split(os.pathsep)
    if dir_str not in paths:
        os.environ["PATH"] = dir_str + os.pathsep + current_path


def _bundled_binary() -> str | None:
    """The FFmpeg shipped in the app's bin directory, unless it is a truncated download."""
    target = BIN_DIR / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if not target.is_file() or target.stat().st_size <= _MIN_BUNDLED_BINARY_BYTES:
        return None
    _ensure_in_path(BIN_DIR)
    return str(target.resolve())


def _system_binary() -> str | None:
    resolved = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    return str(Path(resolved).resolve()) if resolved and Path(resolved).is_file() else None


def get_ffmpeg_binary() -> str | None:
    global _CACHED_FFMPEG_PATH
    if _CACHED_FFMPEG_PATH and Path(_CACHED_FFMPEG_PATH).is_file():
        return _CACHED_FFMPEG_PATH
    found = _bundled_binary() or _system_binary()
    if found:
        _CACHED_FFMPEG_PATH = found
    return found


def ensure_ffmpeg_in_user_data() -> str | None:
    return get_ffmpeg_binary()


def ensure_ffmpeg_available() -> str:
    """Ensure FFmpeg is available, raise error if not."""
    ffmpeg = get_ffmpeg_binary()
    if not ffmpeg:
        error_msg = (
            "FFmpeg is not installed or not in PATH. "
            "MP3 and other compressed formats require FFmpeg. "
            "Install via: brew install ffmpeg (Mac), apt-get install ffmpeg (Linux), "
            "or choco install ffmpeg (Windows)"
        )
        logger.error(error_msg)
        raise FFmpegError(error_msg)
    return ffmpeg


def _convert_to_wav(ffmpeg_cmd: str, media_path: Path, output_wav_path: Path) -> None:
    """Run FFmpeg to produce a 16 kHz mono PCM WAV; a non-zero exit becomes an FFmpegError."""
    cmd = [
        ffmpeg_cmd, "-y", "-i", str(media_path), "-vn",
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(output_wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=_CONVERSION_TIMEOUT_S)
    if result.returncode != 0:
        logger.error(f"FFmpeg conversion failed: {result.stderr}")
        raise FFmpegError("FFmpeg conversion failed", stderr=result.stderr, returncode=result.returncode)


def extract_audio_track(media_path: Path, output_wav_path: Path, validate: bool = True) -> Tuple[Path, bool]:
    """
    Extract audio from video or audio file to 16 kHz mono WAV using ffmpeg.

    Args:
        media_path: Path to source media file
        output_wav_path: Path where WAV file should be written
        validate: If True, validate the output file after extraction

    Returns:
        Tuple of (output_path, success_flag)
        - output_path: Path to the WAV file (output_wav_path if successful, media_path if already WAV)
        - success_flag: True if extraction was successful or file was already WAV

    Raises:
        FFmpegError: If FFmpeg processing fails and validation is enabled
    """
    if media_path.suffix.lower() == ".wav":
        # Already WAV, no conversion needed
        return media_path, True

    ffmpeg_cmd = ensure_ffmpeg_available()  # fail early when FFmpeg is missing
    try:
        _convert_to_wav(ffmpeg_cmd, media_path, output_wav_path)
        if validate:
            _validate_output_wav(output_wav_path, media_path)
        logger.info(f"Successfully extracted audio: {media_path.name} → {output_wav_path.name}")
        return output_wav_path, True
    except FFmpegError:
        raise
    except (subprocess.TimeoutExpired, TimeoutError):
        error_msg = "FFmpeg audio extraction timeout"
        logger.error(error_msg)
        raise FFmpegError(error_msg)
    except Exception as exc:
        error_msg = f"Unexpected error during FFmpeg audio extraction: {exc}"
        logger.error(error_msg)
        raise FFmpegError(error_msg)


def _check_output_file(output_path: Path) -> None:
    if not output_path.exists():
        raise FFmpegError(f"Output file was not created: {output_path}")
    file_size = output_path.stat().st_size
    if file_size == 0:
        raise FFmpegError(f"Output file is empty (0 bytes): {output_path}")
    if file_size < _SUSPICIOUSLY_SMALL_BYTES:
        logger.warning(f"Output file is very small ({file_size} bytes): {output_path}")


def _check_duration(stdout: str) -> None:
    try:
        duration = float(stdout.strip())
    except ValueError:
        raise FFmpegError(f"Could not parse output WAV duration: {stdout}")
    if duration <= 0:
        raise FFmpegError(f"Output WAV has zero or negative duration: {duration}s")
    logger.debug(f"Output WAV validated: {duration:.1f}s duration")


def _probe_output(ffprobe_cmd: str, output_path: Path) -> None:
    cmd = [ffprobe_cmd, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_PROBE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise FFmpegError("Output WAV validation timeout")
    if result.returncode != 0:
        raise FFmpegError(f"Output WAV validation failed: {result.stderr}")
    _check_duration(result.stdout)


def _validate_output_wav(output_path: Path, source_path: Path) -> None:
    """
    Validate that FFmpeg output is a valid WAV file.

    Checks:
    - Output file exists and is not empty
    - Output file can be read by ffprobe
    - Output file has reasonable duration

    Args:
        output_path: Path to the generated WAV file
        source_path: Path to the original source file (for comparison)

    Raises:
        FFmpegError: If validation fails
    """
    _check_output_file(output_path)
    ffprobe_cmd = shutil.which("ffprobe")
    if not ffprobe_cmd:
        logger.warning("ffprobe not available for output validation")
        return
    _probe_output(ffprobe_cmd, output_path)

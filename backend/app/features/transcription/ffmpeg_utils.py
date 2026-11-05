import os
import shutil
import subprocess
import sys
from pathlib import Path
from app.core.settings import BIN_DIR

_CACHED_FFMPEG_PATH: str | None = None


def _ensure_in_path(directory: Path) -> None:
    dir_str = str(directory)
    current_path = os.environ.get("PATH", "")
    paths = current_path.split(os.pathsep)
    if dir_str not in paths:
        os.environ["PATH"] = dir_str + os.pathsep + current_path


def get_ffmpeg_binary() -> str | None:
    global _CACHED_FFMPEG_PATH
    if _CACHED_FFMPEG_PATH and Path(_CACHED_FFMPEG_PATH).is_file():
        return _CACHED_FFMPEG_PATH

    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    target = BIN_DIR / exe_name

    if target.is_file() and target.stat().st_size > 10000:
        _ensure_in_path(BIN_DIR)
        _CACHED_FFMPEG_PATH = str(target.resolve())
        return _CACHED_FFMPEG_PATH

    resolved = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if resolved and Path(resolved).is_file():
        _CACHED_FFMPEG_PATH = str(Path(resolved).resolve())
        return _CACHED_FFMPEG_PATH

    return None


def ensure_ffmpeg_in_user_data() -> str | None:
    return get_ffmpeg_binary()


def extract_audio_track(media_path: Path, output_wav_path: Path) -> Path:
    """Extract audio from video or audio file to 16 kHz mono WAV using ffmpeg."""
    suffix = media_path.suffix.lower()
    if suffix == ".wav":
        return media_path

    ffmpeg_cmd = get_ffmpeg_binary()
    if not ffmpeg_cmd:
        return media_path

    try:
        cmd = [
            ffmpeg_cmd,
            "-y",
            "-i",
            str(media_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output_wav_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_wav_path
    except Exception:
        return media_path

import os
import sys
from pathlib import Path
from app.core.settings import BIN_DIR

_CACHED_FFMPEG_PATH: str | None = None


def _ensure_in_path(directory: Path) -> None:
    """Prepends directory to os.environ['PATH'] if not present."""
    dir_str = str(directory)
    current_path = os.environ.get("PATH", "")
    paths = current_path.split(os.pathsep)
    if dir_str not in paths:
        os.environ["PATH"] = dir_str + os.pathsep + current_path


def get_ffmpeg_binary() -> str | None:
    """
    Locates FFmpeg executable strictly in the application's bin directory in LOCALAPPDATA:
      %LOCALAPPDATA%/funcassist/bin/ffmpeg.exe
    Does not validate or search any other locations.
    """
    global _CACHED_FFMPEG_PATH
    if _CACHED_FFMPEG_PATH and Path(_CACHED_FFMPEG_PATH).is_file():
        return _CACHED_FFMPEG_PATH

    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    target = BIN_DIR / exe_name

    if target.is_file() and target.stat().st_size > 10000:
        _ensure_in_path(BIN_DIR)
        _CACHED_FFMPEG_PATH = str(target.resolve())
        return _CACHED_FFMPEG_PATH

    return None


def ensure_ffmpeg_in_user_data() -> str | None:
    """Returns the FFmpeg path in the application bin directory if present."""
    return get_ffmpeg_binary()

import os
import shutil
import sys
from pathlib import Path
from app.core.settings import ROOT_DIR, USER_DATA_DIR

_CACHED_FFMPEG_PATH: str | None = None


def _find_source_ffmpeg() -> str | None:
    """Searches bundled, repo, and external locations for FFmpeg (excluding user data directory)."""
    candidates: list[Path] = []

    # 1. Explicit environment variable
    env_ffmpeg = os.environ.get("FFMPEG_PATH") or os.environ.get("FFMPEG_BINARY")
    if env_ffmpeg:
        candidates.append(Path(env_ffmpeg))

    # 2. Next to running Python executable (portable / bundled venv)
    py_dir = Path(sys.executable).parent
    candidates.extend([
        py_dir / "ffmpeg.exe",
        py_dir / "ffmpeg",
        py_dir / "bin" / "ffmpeg.exe",
        py_dir / "bin" / "ffmpeg",
        py_dir.parent / "bin" / "ffmpeg.exe",
        py_dir.parent / "ffmpeg.exe",
    ])

    # 3. Project workspace / Tauri bundle paths
    candidates.extend([
        ROOT_DIR / "src-tauri" / "bin" / "ffmpeg.exe",
        ROOT_DIR / "src-tauri" / "bin" / "ffmpeg",
        ROOT_DIR / "bin" / "ffmpeg.exe",
        ROOT_DIR / "bin" / "ffmpeg",
        ROOT_DIR / "ffmpeg.exe",
        ROOT_DIR / "backend" / "bin" / "ffmpeg.exe",
    ])

    # 4. Standard Windows installer locations (Program Files & LocalAppData)
    if sys.platform == "win32":
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            base_local = Path(local_app_data)
            candidates.extend([
                base_local / "Programs" / "FuncAssist" / "resources" / "bin" / "ffmpeg.exe",
                base_local / "Programs" / "FuncAssist" / "bin" / "ffmpeg.exe",
                base_local / "Programs" / "FuncAssist" / "ffmpeg.exe",
                base_local / "QA Project Management" / "bin" / "ffmpeg.exe",
            ])

        program_files = os.getenv("ProgramFiles")
        if program_files:
            base_pf = Path(program_files)
            candidates.extend([
                base_pf / "FuncAssist" / "resources" / "bin" / "ffmpeg.exe",
                base_pf / "FuncAssist" / "bin" / "ffmpeg.exe",
                base_pf / "FuncAssist" / "ffmpeg.exe",
            ])

    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 10000:
            return str(candidate.resolve())

    # 5. Check system PATH
    system_which = shutil.which("ffmpeg") or (shutil.which("ffmpeg.exe") if sys.platform == "win32" else None)
    if system_which:
        return str(Path(system_which).resolve())

    return None


def ensure_ffmpeg_in_user_data() -> str | None:
    """
    Ensures FFmpeg executable is copied to the root of the application's AppData/Local folder:
      - %LOCALAPPDATA%/funcassist/ffmpeg.exe
    If missing, locates a bundled, repo, or system version and copies it there.
    Returns the resolved path in AppData/Local, or None if not available.
    """
    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    target_root = USER_DATA_DIR / exe_name

    # If already present and valid in root
    if target_root.is_file() and target_root.stat().st_size > 10000:
        _ensure_in_path(USER_DATA_DIR)
        return str(target_root.resolve())

    # Not found in USER_DATA_DIR yet - locate source and copy into root of AppData/Local/funcassist
    source = _find_source_ffmpeg()
    if source and Path(source).is_file():
        try:
            USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target_root)
            _ensure_in_path(USER_DATA_DIR)
            return str(target_root.resolve())
        except Exception as e:
            print(f"Warning: Failed to copy FFmpeg to AppData/Local root {target_root}: {e}")

    return None


def get_ffmpeg_binary() -> str | None:
    """
    Locates the FFmpeg executable, prioritizing the root of AppData/Local/funcassist/ffmpeg.exe.
    Automatically copies bundled FFmpeg to AppData/Local root if not already present.
    Prepends the directory containing ffmpeg to PATH so third-party libraries
    (like openai-whisper) can invoke it without errors.
    """
    global _CACHED_FFMPEG_PATH
    if _CACHED_FFMPEG_PATH and Path(_CACHED_FFMPEG_PATH).is_file():
        return _CACHED_FFMPEG_PATH

    # 1. Ensure and locate in root of AppData/Local
    in_user_data = ensure_ffmpeg_in_user_data()
    if in_user_data:
        _CACHED_FFMPEG_PATH = in_user_data
        return in_user_data

    # 2. Fallback to any external or system source
    external_source = _find_source_ffmpeg()
    if external_source:
        _ensure_in_path(Path(external_source).parent)
        _CACHED_FFMPEG_PATH = external_source
        return external_source

    return None


def _ensure_in_path(directory: Path) -> None:
    """Prepends directory to os.environ['PATH'] if not present."""
    dir_str = str(directory)
    current_path = os.environ.get("PATH", "")
    paths = current_path.split(os.pathsep)
    if dir_str not in paths:
        os.environ["PATH"] = dir_str + os.pathsep + current_path

import os
import sys
import multiprocessing
from pathlib import Path
# Force UTF-8 mode on Windows before importing anything
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
if sys.stdout and hasattr(sys.stdout, "encoding") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "encoding") and sys.stderr.encoding != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Fix working directory and import paths for frozen/PyInstaller executables
if getattr(sys, "frozen", False):
    base_dir = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))
    backend_dir = base_dir / "backend"
    if backend_dir.is_dir() and str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
else:
    root_backend = Path(__file__).resolve().parent
    if str(root_backend) not in sys.path:
        sys.path.insert(0, str(root_backend))

import uvicorn
from app.core.settings import get_settings


def main():
    multiprocessing.freeze_support()
    settings = get_settings()

    port = settings.server_port or 6728
    host = settings.server_host or "127.0.0.1"

    # In production/frozen mode, reload must be False
    reload_mode = not getattr(sys, "frozen", False)

    print(f"Starting FuncAssist server on http://{host}:{port} (reload={reload_mode})...")

    # Use app instance directly instead of string import to ensure frozen compatibility
    if getattr(sys, "frozen", False):
        from app.main import app
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
        )
    else:
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
            reload=reload_mode,
            log_level="info",
        )


if __name__ == "__main__":
    main()

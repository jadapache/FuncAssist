import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
ENTRYPOINT = BACKEND_DIR / "run_server.py"
OUTPUT_DIR = ROOT_DIR / "src-tauri" / "bin"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

pyinstaller_cmd = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name",
    "funcassist-backend",
    "--distpath",
    str(OUTPUT_DIR),
    "--workpath",
    str(ROOT_DIR / "build" / "pyinstaller"),
    "--specpath",
    str(ROOT_DIR / "build"),
    "--paths",
    str(BACKEND_DIR),
    "--add-data",
    f"{BACKEND_DIR / 'app'};app",
    "--hidden-import",
    "uvicorn.logging",
    "--hidden-import",
    "uvicorn.loops.auto",
    "--hidden-import",
    "uvicorn.protocols.http.auto",
    "--hidden-import",
    "uvicorn.lifespan.on",
    "--hidden-import",
    "tiktoken_ext",
    "--hidden-import",
    "tiktoken_ext.openai_public",
    "--hidden-import",
    "keyring.backends.Windows",
    "--collect-all",
    "fastapi",
    "--collect-all",
    "uvicorn",
    "--collect-all",
    "litellm",
    "--collect-all",
    "tiktoken",
    "--collect-all",
    "tiktoken_ext",
    "--collect-all",
    "keyring",
    "--collect-all",
    "whisper",
    "--collect-all",
    "faster_whisper",
    str(ENTRYPOINT),
]

print("Running PyInstaller to produce funcassist-backend.exe...")
result = subprocess.run(pyinstaller_cmd, cwd=str(ROOT_DIR))
if result.returncode == 0:
    print("\nSUCCESS: funcassist-backend.exe generated at", OUTPUT_DIR / "funcassist-backend.exe")
sys.exit(result.returncode)

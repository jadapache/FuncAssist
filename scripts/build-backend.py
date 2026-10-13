import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SPEC_FILE = ROOT_DIR / "backend" / "funcassist-backend.spec"
OUTPUT_DIR = ROOT_DIR / "src-tauri" / "bin"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

pyinstaller_cmd = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--distpath",
    str(OUTPUT_DIR),
    "--workpath",
    str(ROOT_DIR / "build" / "pyinstaller"),
    str(SPEC_FILE),
]

print(f"Running PyInstaller with spec: {SPEC_FILE}...")
result = subprocess.run(pyinstaller_cmd, cwd=str(ROOT_DIR))
if result.returncode == 0:
    print("\nSUCCESS: funcassist-backend.exe generated at", OUTPUT_DIR / "funcassist-backend.exe")
sys.exit(result.returncode)

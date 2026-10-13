import os
import sys
import multiprocessing
from pathlib import Path

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

# Prevent LiteLLM remote sync fetch
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

# Fix for tiktoken dynamic plugin discovery in PyInstaller frozen executables
try:
    import tiktoken.registry
    import tiktoken_ext.openai_public

    tiktoken.registry._available_plugin_modules = lambda: ["tiktoken_ext.openai_public"]
    if tiktoken.registry.ENCODING_CONSTRUCTORS is None:
        tiktoken.registry.ENCODING_CONSTRUCTORS = dict(tiktoken_ext.openai_public.ENCODING_CONSTRUCTORS)
    else:
        tiktoken.registry.ENCODING_CONSTRUCTORS.update(tiktoken_ext.openai_public.ENCODING_CONSTRUCTORS)
except Exception as e:
    print(f"Warning initializing tiktoken: {e}", file=sys.stderr)

# Ensure Windows Credential Manager keyring backend is registered if on Windows
if sys.platform == "win32":
    try:
        import keyring
        import keyring.backends.Windows

        keyring.set_keyring(keyring.backends.Windows.WinVaultKeyring())
    except Exception as e:
        print(f"Warning initializing keyring: {e}", file=sys.stderr)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    import uvicorn
    from app.main import app

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        access_log=False,
    )

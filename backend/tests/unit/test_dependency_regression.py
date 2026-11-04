from __future__ import annotations

import sys
from pathlib import Path
import pytest
from app.ai.providers.registry import FORBIDDEN_BACKEND_PROVIDERS
from app.ai.providers.factory import resolve_provider


def test_no_legacy_inference_libraries_in_sys_modules():
  forbidden_modules = [
    "whisper",
    "faster_whisper",
    "onnxruntime",
    "llama_cpp",
    "ctranslate2",
  ]
  for mod in forbidden_modules:
    assert mod not in sys.modules, f"Forbidden module '{mod}' should not be loaded"


def test_factory_rejects_forbidden_providers():
  for prov in FORBIDDEN_BACKEND_PROVIDERS:
    with pytest.raises(ValueError, match="no se ejecuta en el backend"):
      resolve_provider(provider_name=prov, model_name="test-model")


def test_factory_rejects_gguf_models():
  with pytest.raises(ValueError, match="GGUF"):
    resolve_provider(provider_name="groq", model_name="llama.gguf")


def test_backend_codebase_has_no_local_model_execution():
  backend_app = Path(__file__).resolve().parent.parent.parent / "app"
  forbidden_terms = [
    "import whisper\n",
    "from whisper import",
    "import faster_whisper",
    "import llama_cpp",
    "import onnxruntime",
  ]
  for py_file in backend_app.rglob("*.py"):
    content = py_file.read_text(encoding="utf-8")
    for term in forbidden_terms:
      assert term not in content, f"Found forbidden runtime reference '{term}' in {py_file}"

import pytest

from app.ai.dlp import enforce_cloud_policy, sanitize_text
from app.ai.errors import AIError


def test_sanitize_removes_personal_data_and_secrets():
  text = (
    "Contacto: ana.perez@fcv.org, cel 315 555 1234, CC 1.098.765.432, "
    "token ghp_abcdefghijklmnopqrstuvwxyz123456 y password: Secreta123!"
  )
  clean = sanitize_text(text)
  for leaked in ("ana.perez@fcv.org", "315 555 1234", "1.098.765.432", "ghp_", "Secreta123!"):
    assert leaked not in clean
  assert "[EMAIL]" in clean and "[TELEFONO]" in clean and "[DOCUMENTO]" in clean and "[SECRETO]" in clean


def test_confidential_content_is_blocked_for_cloud():
  with pytest.raises(AIError) as exc:
    enforce_cloud_policy([{"role": "user", "content": "Documento CONFIDENCIAL: plan de negocio"}], "OpenAI")
  assert exc.value.code == "confidential_data_blocked"


def test_internal_content_passes_sanitized():
  out = enforce_cloud_policy([{"role": "user", "content": "Escribe a luis@fcv.org"}], "Groq Cloud")
  assert out[0]["content"] == "Escribe a [EMAIL]"

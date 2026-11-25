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


def test_system_prompts_written_by_the_application_are_not_blocked():
  from app.ai.untrusted import UNTRUSTED_NOTICE

  system = {"role": "system", "content": "Documento CONFIDENCIAL de ejemplo. " + UNTRUSTED_NOTICE}
  out = enforce_cloud_policy([system, {"role": "user", "content": "hola"}], "OpenAI")
  assert out[0]["content"].startswith("Documento CONFIDENCIAL")


def test_external_content_in_a_system_message_is_checked_like_any_other():
  from app.ai.untrusted import wrap_untrusted

  leaked = "Reglas. " + wrap_untrusted("jira", "K-1", "Historia clínica del paciente")
  with pytest.raises(AIError) as exc:
    enforce_cloud_policy([{"role": "system", "content": leaked}], "OpenAI")
  assert exc.value.code == "confidential_data_blocked"


def test_external_content_in_a_system_message_is_sanitized():
  from app.ai.untrusted import wrap_untrusted

  leaked = wrap_untrusted("jira", "K-2", "Escribe a luis@fcv.org")
  out = enforce_cloud_policy([{"role": "system", "content": leaked}], "Groq")
  assert "luis@fcv.org" not in out[0]["content"] and "[EMAIL]" in out[0]["content"]


def test_system_message_as_content_parts_is_checked_too():
  from app.ai.untrusted import wrap_untrusted

  parts = [{"type": "text", "text": wrap_untrusted("jira", "K-3", "datos de pacientes")}]
  with pytest.raises(AIError):
    enforce_cloud_policy([{"role": "system", "content": parts}], "OpenAI")

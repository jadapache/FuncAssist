"""Data Loss Prevention for prompts sent to cloud AI providers.

Policy (see docs/SECURITY_COMPLIANCE.md):
- Content classified as CONFIDENTIAL is processed only by on-premise engines (WebLLM). Remote Ollama is a third-party endpoint and is treated as cloud.
  Any message carrying a confidential marker is blocked before reaching a cloud provider.
- INTERNAL content may go to cloud providers after sanitization: personal identifiers and
  secrets are replaced with placeholders so they never leave the organization.
"""

from __future__ import annotations

import re
from typing import Any

from app.ai.errors import AIError
from app.ai.untrusted import contains_envelope

# Markers that classify a text as confidential (case-insensitive).
CONFIDENTIAL_MARKERS = re.compile(
  r"\b(confidencial|confidential|clasificaci[oó]n:\s*confidencial|datos?\s+de\s+pacientes?|historia\s+cl[ií]nica)\b",
  re.IGNORECASE,
)

_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
  # Secrets first so their digits are not partially matched by the numeric rules.
  (re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_\-]{16,}\b"), "[SECRETO]"),
  (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_\-]{20,}|AIza[0-9A-Za-z_\-]{30,}|gsk_[A-Za-z0-9]{20,})\b"), "[SECRETO]"),
  (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"), "[SECRETO]"),
  (re.compile(r"(?i)\b(password|contrase[ñn]a|passwd|pwd)\s*[:=]\s*\S+"), r"\1: [SECRETO]"),
  (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
  # Colombian ID documents (CC/TI/CE/NIT) with an explicit prefix.
  (re.compile(r"(?i)\b(c\.?c\.?|t\.?i\.?|c\.?e\.?|nit|c[eé]dula|documento)\s*(n[°oº.]*\s*)?:?\s*\d[\d.\-]{5,14}\d\b"), "[DOCUMENTO]"),
  # Mobile numbers (Colombia +57 3xx) and generic international phone numbers.
  (re.compile(r"(?<!\d)(\+?57[\s\-]?)?3\d{2}[\s\-]?\d{3}[\s\-]?\d{4}(?!\d)"), "[TELEFONO]"),
  (re.compile(r"(?<!\d)\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}(?!\d)"), "[TARJETA]"),
]


def is_confidential(text: str) -> bool:
  return bool(CONFIDENTIAL_MARKERS.search(text or ""))


def sanitize_text(text: str) -> str:
  for pattern, replacement in _REDACTIONS:
    text = pattern.sub(replacement, text)
  return text


def _iter_text_parts(content: Any):
  if isinstance(content, str):
    yield content
  elif isinstance(content, list):
    for part in content:
      if isinstance(part, dict) and isinstance(part.get("text"), str):
        yield part["text"]


def _sanitize_content(content: Any) -> Any:
  if isinstance(content, str):
    return sanitize_text(content)
  if isinstance(content, list):
    out = []
    for part in content:
      if isinstance(part, dict) and isinstance(part.get("text"), str):
        part = {**part, "text": sanitize_text(part["text"])}
      out.append(part)
    return out
  return content


def enforce_cloud_policy(messages: list[dict[str, Any]], provider_name: str) -> list[dict[str, Any]]:
  """Block confidential content and sanitize the rest before a cloud provider call."""
  for message in messages:
    texts = list(_iter_text_parts(message.get("content")))
    if message.get("role") == "system" and not any(contains_envelope(t) for t in texts):
      continue  # system prompts are application-authored templates, unless external content ended up in one
    if any(is_confidential(text) for text in texts):
      raise AIError(
        "confidential_data_blocked",
        f"El contenido está clasificado como confidencial y no puede enviarse a {provider_name}. "
        "Usa el modelo en el navegador.",
      )
  return [{**m, "content": _sanitize_content(m.get("content"))} for m in messages]

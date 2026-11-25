from __future__ import annotations

from docx.shared import RGBColor

from app.features.markdown_docx import DocxStyle, render_markdown_docx

_ACTION_WORDS = ("validar", "verificar", "confirmar", "comprobar")


def _is_action_or_placeholder(text: str) -> bool:
  """Numbered steps that start with an action word, or with a {{placeholder}}, stay as list items."""
  return text.lower().startswith(_ACTION_WORDS) or text.startswith("{{")


STYLE = DocxStyle(
  primary=RGBColor(30, 58, 138),     # #1E3A8A Dark Navy
  secondary=RGBColor(15, 23, 42),    # #0F172A Slate
  header_hex="1E3A8A",
  alt_row_hex="F8FAFC",
  subtitle="Generado automáticamente por FuncAssist - Módulo Funcional",
  title_size=20,
  title_space_after=6,
  subtitle_space_after=18,
  h1_size=16,
  h2_size=13,
  h3_size=11.5,
  bullet_markers=("- ", "* "),
  rejects_section_title=_is_action_or_placeholder,
)


def create_mejoras_docx(markdown_content: str, title: str = "Documento de Mejora y Requerimientos Funcionales") -> bytes:
  return render_markdown_docx(markdown_content, title, STYLE)

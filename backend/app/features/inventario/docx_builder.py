from __future__ import annotations

from docx.shared import RGBColor

from app.features.markdown_docx import DocxStyle, render_markdown_docx

STYLE = DocxStyle(
  primary=RGBColor(0, 39, 119),      # #002777 Corporate Blue
  secondary=RGBColor(0, 68, 151),    # #004497 Navy Accent
  header_hex="002777",
  alt_row_hex="F1F5F9",
  subtitle="Generado a partir de Minutas y Transcripciones de Reunión - FuncAssist",
)


def create_inventario_docx(markdown_content: str, title: str = "Inventario de Requerimientos y Contexto de Proyecto") -> bytes:
  return render_markdown_docx(markdown_content, title, STYLE)

from __future__ import annotations

from docx.shared import RGBColor

from app.features.markdown_docx import DocxStyle, render_markdown_docx

STYLE = DocxStyle(
  primary=RGBColor(0, 39, 119),      # #002777 Corporate Navy
  secondary=RGBColor(0, 68, 151),    # #004497 Navy Accent
  header_hex="002777",
  alt_row_hex="F8FAFC",
  subtitle="Documentación Funcional y Criterios de Aceptación - FuncAssist",
  checked_color=RGBColor(5, 150, 105),  # #059669 Green
)


def create_levantamiento_docx(
  markdown_content: str,
  title: str = "Levantamiento Detallado de Requerimientos y Especificación Funcional",
) -> bytes:
  return render_markdown_docx(markdown_content, title, STYLE)

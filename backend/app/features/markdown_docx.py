"""Markdown to Word: the engine behind the inventario, levantamiento and mejoras documents.

Each document only supplies a `DocxStyle` (colors, sizes, subtitle and a couple of rules); the way markdown is
turned into paragraphs, lists, quotes, code and tables is the same for all of them.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Callable

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Inches, Pt, RGBColor

TEXT_COLOR = RGBColor(51, 65, 85)       # #334155 Dark Gray
QUOTE_COLOR = RGBColor(71, 85, 105)
SUBTITLE_COLOR = RGBColor(100, 116, 139)
FONT = "Segoe UI"

_TABLE_ROW = re.compile(r"^\|[\s\-:|]+\|$")
_NUMBERED = re.compile(r"^\d+\.\s")


@dataclass(frozen=True)
class DocxStyle:
  primary: RGBColor
  secondary: RGBColor
  header_hex: str
  alt_row_hex: str
  subtitle: str
  title_size: float = 18
  title_space_after: float = 4
  subtitle_space_after: float = 16
  h1_size: float = 15
  h2_size: float = 12.5
  h3_size: float = 11
  bullet_markers: tuple[str, ...] = ("- ", "* ", "• ")
  # Draws "- [ ]" and "- [x]" items as check boxes, the checked ones in this color.
  checked_color: RGBColor | None = None
  # Numbered lines that must stay list items even when they look like a section title.
  rejects_section_title: Callable[[str], bool] = field(default=lambda text: False)


def set_cell_background(cell, hex_color: str) -> None:
  tc_pr = cell._element.get_or_add_tcPr()
  tc_pr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>'))


def add_formatted_runs(paragraph, text: str, italic: bool = False, color: RGBColor | None = None) -> None:
  """Adds the text to the paragraph, turning **bold** markers into bold runs."""
  for part in re.split(r"(\*\*.*?\*\*)", text):
    if part.startswith("**") and part.endswith("**"):
      run = paragraph.add_run(part[2:-2])
      run.font.bold = True
    else:
      run = paragraph.add_run(part)
      if italic:
        run.font.italic = True
    run.font.name = FONT
    run.font.size = Pt(10.5)
    run.font.color.rgb = color if color else TEXT_COLOR


def is_section_title(text: str) -> bool:
  """Whether a numbered line reads as a section title instead of a list item."""
  return (
    3 <= len(text) <= 80
    and not text.endswith((".", ",", ";", ":"))
    and (text == text.upper() or text[0].isupper())
    and " " in text
  )


def render_table(doc, rows: list[list[str]], style: DocxStyle) -> None:
  if not rows:
    return
  table = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows))
  table.alignment = WD_TABLE_ALIGNMENT.CENTER
  table.style = "Table Grid"
  for r_idx, row_data in enumerate(rows):
    row = table.rows[r_idx]
    for c_idx, value in enumerate(row_data):
      _fill_cell(row.cells[c_idx], value, r_idx, style)


def _fill_cell(cell, value: str, row_index: int, style: DocxStyle) -> None:
  cell.text = ""
  paragraph = cell.paragraphs[0]
  paragraph.paragraph_format.space_before = Pt(3)
  paragraph.paragraph_format.space_after = Pt(3)
  is_header = row_index == 0
  if is_header:
    set_cell_background(cell, style.header_hex)
  elif row_index % 2 == 1:
    set_cell_background(cell, style.alt_row_hex)
  run = paragraph.add_run(value)
  run.font.name = FONT
  run.font.size = Pt(10 if is_header else 9.5)
  if is_header:
    run.font.bold = True
  run.font.color.rgb = RGBColor(255, 255, 255) if is_header else TEXT_COLOR


class _Renderer:
  def __init__(self, style: DocxStyle) -> None:
    self.style = style
    self.doc = Document()
    self.in_code = False
    self.table_rows: list[list[str]] = []

  def render(self, markdown: str, title: str) -> bytes:
    self._set_margins()
    self._title(title)
    for line in markdown.splitlines():
      self._line(line)
    if self.table_rows:
      render_table(self.doc, self.table_rows, self.style)
    buffer = io.BytesIO()
    self.doc.save(buffer)
    return buffer.getvalue()

  def _set_margins(self) -> None:
    for section in self.doc.sections:
      section.top_margin = section.bottom_margin = Inches(1)
      section.left_margin = section.right_margin = Inches(1)

  def _title(self, title: str) -> None:
    paragraph = self.doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(self.style.title_space_after)
    self._bold_run(paragraph, title.upper(), self.style.title_size, self.style.primary)

    subtitle = self.doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(self.style.subtitle_space_after)
    run = subtitle.add_run(self.style.subtitle)
    run.font.name = FONT
    run.font.size = Pt(9.5)
    run.font.italic = True
    run.font.color.rgb = SUBTITLE_COLOR

  @staticmethod
  def _bold_run(paragraph, text: str, size: float, color: RGBColor) -> None:
    run = paragraph.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = True
    run.font.color.rgb = color

  def _line(self, line: str) -> None:
    stripped = line.strip()
    if stripped.startswith("```"):
      self.in_code = not self.in_code
    elif self.in_code:
      self._code(line)
    elif self._table_line(stripped):
      pass
    elif stripped:
      self._block(stripped)

  def _table_line(self, stripped: str) -> bool:
    """Collects table rows. A line that ends the table flushes it and is then handled as a normal line."""
    if stripped.startswith("|") and stripped.endswith("|"):
      if not _TABLE_ROW.match(stripped):
        self.table_rows.append([c.strip() for c in stripped.split("|")[1:-1]])
      return True
    if self.table_rows:
      render_table(self.doc, self.table_rows, self.style)
      self.table_rows = []
    return False

  def _code(self, line: str) -> None:
    paragraph = self.doc.add_paragraph()
    paragraph.paragraph_format.left_indent = Inches(0.4)
    paragraph.paragraph_format.space_after = Pt(2)
    run = paragraph.add_run(line)
    run.font.name = "Consolas"
    run.font.size = Pt(9.5)
    run.font.color.rgb = QUOTE_COLOR

  def _block(self, text: str) -> None:
    if not (
      self._heading(text)
      or self._checklist_item(text)
      or self._bullet(text)
      or self._numbered(text)
      or self._quote(text)
    ):
      paragraph = self.doc.add_paragraph()
      paragraph.paragraph_format.space_after = Pt(6)
      paragraph.paragraph_format.line_spacing = 1.15
      add_formatted_runs(paragraph, text)

  def _heading_paragraph(self, text: str, before: float, after: float, size: float, color: RGBColor) -> None:
    paragraph = self.doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)
    self._bold_run(paragraph, text, size, color)

  def _heading(self, text: str) -> bool:
    style = self.style
    levels = (
      ("# ", 16, 6, style.h1_size, style.primary),
      ("## ", 14, 4, style.h2_size, style.primary),
      ("### ", 10, 2, style.h3_size, style.secondary),
    )
    for marker, before, after, size, color in levels:
      if text.startswith(marker):
        self._heading_paragraph(text[len(marker):], before, after, size, color)
        return True
    return False

  def _checklist_item(self, text: str) -> bool:
    if self.style.checked_color is None or not text.startswith(("- [ ] ", "- [x] ")):
      return False
    checked = "[x]" in text
    paragraph = self.doc.add_paragraph(style="List Bullet")
    paragraph.paragraph_format.space_after = Pt(3)
    run = paragraph.add_run("[✓] " if checked else "[ ] ")
    run.font.bold = True
    run.font.color.rgb = self.style.checked_color if checked else self.style.primary
    add_formatted_runs(paragraph, text[6:])
    return True

  def _bullet(self, text: str) -> bool:
    if not text.startswith(self.style.bullet_markers):
      return False
    paragraph = self.doc.add_paragraph(style="List Bullet")
    paragraph.paragraph_format.space_after = Pt(3)
    add_formatted_runs(paragraph, text[2:])
    return True

  def _numbered(self, text: str) -> bool:
    if not _NUMBERED.match(text):
      return False
    remaining = re.sub(r"^\d+\.\s*", "", text)
    if is_section_title(remaining) and not self.style.rejects_section_title(remaining):
      self._heading_paragraph(text, 14, 4, self.style.h2_size, self.style.primary)
    else:
      paragraph = self.doc.add_paragraph(style="List Number")
      paragraph.paragraph_format.space_after = Pt(3)
      add_formatted_runs(paragraph, re.sub(r"^\d+\.\s", "", text))
    return True

  def _quote(self, text: str) -> bool:
    if not text.startswith("> "):
      return False
    paragraph = self.doc.add_paragraph()
    paragraph.paragraph_format.left_indent = Inches(0.3)
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(4)
    add_formatted_runs(paragraph, text[2:], italic=True, color=QUOTE_COLOR)
    return True


def render_markdown_docx(markdown_content: str, title: str, style: DocxStyle) -> bytes:
  return _Renderer(style).render(markdown_content, title)

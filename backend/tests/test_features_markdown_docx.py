"""The markdown to Word engine, checked through the documents it produces."""

from __future__ import annotations

import io

import pytest
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, RGBColor

from app.features.markdown_docx import (
  DocxStyle,
  add_formatted_runs,
  is_section_title,
  render_markdown_docx,
  render_table,
)

PRIMARY = RGBColor(1, 2, 3)
SECONDARY = RGBColor(4, 5, 6)
CHECKED = RGBColor(7, 8, 9)
STYLE = DocxStyle(
  primary=PRIMARY, secondary=SECONDARY, header_hex="AA0000", alt_row_hex="00BB00", subtitle="Subtítulo",
  title_size=21, title_space_after=7, subtitle_space_after=9, h1_size=17, h2_size=14, h3_size=12,
  checked_color=CHECKED,
)


def render(markdown: str, style: DocxStyle = STYLE, title: str = "Mi título"):
  return Document(io.BytesIO(render_markdown_docx(markdown, title, style)))


def body(markdown: str, style: DocxStyle = STYLE):
  """The paragraphs after the title and the subtitle."""
  return render(markdown, style).paragraphs[2:]


def points(length) -> float:
  return length.pt


def test_the_page_has_one_inch_margins():
  section = render("").sections[0]
  assert [section.top_margin, section.bottom_margin, section.left_margin, section.right_margin] == [Inches(1)] * 4


def test_the_title_and_subtitle_use_the_style():
  title, subtitle = render("").paragraphs[:2]
  assert title.text == "MI TÍTULO" and title.alignment == WD_ALIGN_PARAGRAPH.LEFT
  assert (points(title.paragraph_format.space_before), points(title.paragraph_format.space_after)) == (0, 7)
  run = title.runs[0]
  assert (run.font.name, points(run.font.size), run.font.bold, run.font.color.rgb) == ("Segoe UI", 21, True, PRIMARY)
  assert subtitle.text == "Subtítulo" and points(subtitle.paragraph_format.space_after) == 9
  sub_run = subtitle.runs[0]
  assert (sub_run.font.name, points(sub_run.font.size), sub_run.font.italic) == ("Segoe UI", 9.5, True)
  assert sub_run.font.color.rgb == RGBColor(100, 116, 139)


def test_headings_use_the_sizes_colors_and_spacing_of_their_level():
  h1, h2, h3 = body("# Uno\n## Dos\n### Tres")
  for paragraph, text, size, color, before, after in [
    (h1, "Uno", 17, PRIMARY, 16, 6), (h2, "Dos", 14, PRIMARY, 14, 4), (h3, "Tres", 12, SECONDARY, 10, 2),
  ]:
    run = paragraph.runs[0]
    assert paragraph.text == text and run.font.bold and run.font.name == "Segoe UI"
    assert (points(run.font.size), run.font.color.rgb) == (size, color)
    assert (points(paragraph.paragraph_format.space_before), points(paragraph.paragraph_format.space_after)) == (before, after)


@pytest.mark.parametrize("line", ["#sin espacio", "#### cuarto nivel", "#", "texto # no titulo"])
def test_lines_that_are_not_headings_are_plain_paragraphs(line):
  (paragraph,) = body(line)
  assert paragraph.text == line and paragraph.runs[0].font.bold is not True


def test_a_plain_paragraph_keeps_bold_markers_as_bold_runs():
  (paragraph,) = body("antes **negrita** después")
  assert [(r.text, r.font.bold) for r in paragraph.runs] == [("antes ", None), ("negrita", True), (" después", None)]
  assert all(points(r.font.size) == 10.5 and r.font.color.rgb == RGBColor(51, 65, 85) for r in paragraph.runs)
  assert points(paragraph.paragraph_format.space_after) == 6 and paragraph.paragraph_format.line_spacing == 1.15


def test_plain_text_is_not_italic_and_a_lone_marker_is_not_bold():
  (paragraph,) = body("texto normal")
  assert all(r.font.italic is None for r in paragraph.runs)
  (start,) = body("**solo apertura")
  (end,) = body("solo cierre**")
  assert [(p.text, p.runs[0].font.bold) for p in (start, end)] == [("**solo apertura", None), ("solo cierre**", None)]


def test_blank_and_whitespace_lines_are_skipped():
  assert [p.text for p in body("uno\n\n   \ndos")] == ["uno", "dos"]


def test_bullets_use_the_style_markers():
  paragraphs = body("- a\n* b\n• c")
  assert [(p.text, p.style.name) for p in paragraphs] == [("a", "List Bullet"), ("b", "List Bullet"), ("c", "List Bullet")]
  assert all(points(p.paragraph_format.space_after) == 3 for p in paragraphs)

  narrow = DocxStyle(primary=PRIMARY, secondary=SECONDARY, header_hex="AA0000", alt_row_hex="00BB00",
                     subtitle="s", bullet_markers=("- ",))
  assert [(p.text, p.style.name) for p in body("- a\n* b", narrow)] == [("a", "List Bullet"), ("* b", "Normal")]


def test_check_boxes_show_the_state_of_the_item():
  pending, done, mixed = body("- [ ] pendiente\n- [x] hecho\n- [ ] raro [x] dentro")
  assert [pending.runs[0].text, done.runs[0].text, mixed.runs[0].text] == ["[ ] ", "[✓] ", "[✓] "]
  assert (pending.runs[0].font.bold, pending.runs[0].font.color.rgb) == (True, PRIMARY)
  assert done.runs[0].font.color.rgb == CHECKED and mixed.runs[0].font.color.rgb == CHECKED
  assert pending.runs[1].text == "pendiente" and done.runs[1].text == "hecho"
  assert all(p.style.name == "List Bullet" and points(p.paragraph_format.space_after) == 3 for p in (pending, done))


def test_without_a_checked_color_check_boxes_are_ordinary_bullets():
  plain = DocxStyle(primary=PRIMARY, secondary=SECONDARY, header_hex="AA0000", alt_row_hex="00BB00", subtitle="s")
  (paragraph,) = body("- [x] hecho", plain)
  assert paragraph.text == "[x] hecho" and paragraph.style.name == "List Bullet"


def test_numbered_lines_that_read_as_titles_become_headings():
  (title,) = body("1. Alcance General")
  run = title.runs[0]
  assert title.text == "1. Alcance General" and title.style.name == "Normal"
  assert (points(run.font.size), run.font.bold, run.font.color.rgb) == (14, True, PRIMARY)
  assert (points(title.paragraph_format.space_before), points(title.paragraph_format.space_after)) == (14, 4)


def test_other_numbered_lines_are_list_items_without_their_number():
  paragraphs = body("2. texto en minúscula\n3. Termina con punto.")
  assert [(p.text, p.style.name) for p in paragraphs] == [
    ("texto en minúscula", "List Number"), ("Termina con punto.", "List Number")]
  assert all(points(p.paragraph_format.space_after) == 3 for p in paragraphs)


@pytest.mark.parametrize("text,expected", [
  ("Alcance General", True),
  ("A B", True),            # three characters is the shortest title
  ("AB", False),
  ("Palabra", False),       # a title needs a space
  ("alcance general", False),
  ("ALCANCE GENERAL", True),
  ("12 34", True),          # no letters: equal to its upper case
  ("Termina con punto.", False),
  ("Lista con coma,", False),
  ("Dos puntos:", False),
  ("Punto y coma;", False),
  ("Con admiración!", True),
  ("A" + " " * 78 + "B", True),  # 80 characters is the longest title
  ("A" + " " * 79 + "B", False),
])
def test_what_reads_as_a_section_title(text, expected):
  assert is_section_title(text) is expected


def test_the_style_can_keep_some_numbered_lines_as_list_items():
  style = DocxStyle(primary=PRIMARY, secondary=SECONDARY, header_hex="AA0000", alt_row_hex="00BB00", subtitle="s",
                    rejects_section_title=lambda text: text.startswith("Xenon"))
  kept, title = body("1. Xenon Procedimiento\n2. Alcance General", style)
  assert (kept.style.name, kept.text) == ("List Number", "Xenon Procedimiento")
  assert (title.style.name, title.text) == ("Normal", "2. Alcance General")


def test_a_number_needs_a_space_after_the_dot_to_start_a_list_item():
  (paragraph,) = body("3.Sin espacio")
  assert paragraph.text == "3.Sin espacio" and paragraph.style.name == "Normal"
  (title,) = body("10. Dos Dígitos Título")
  assert title.text == "10. Dos Dígitos Título"


def test_quotes_are_indented_italic_notes():
  (quote,) = body("> una **nota** aquí")
  fmt = quote.paragraph_format
  assert (fmt.left_indent, points(fmt.space_before), points(fmt.space_after)) == (Inches(0.3), 4, 4)
  assert [(r.text, r.font.italic, r.font.bold) for r in quote.runs] == [
    ("una ", True, None), ("nota", None, True), (" aquí", True, None)]
  assert quote.runs[0].font.color.rgb == RGBColor(71, 85, 105)


def test_code_blocks_keep_every_line_as_written():
  paragraphs = body("```python\n  # no es título\n    x = 1\n```\nafuera")
  assert [p.text for p in paragraphs] == ["  # no es título", "    x = 1", "afuera"]
  code = paragraphs[0]
  assert (code.paragraph_format.left_indent, points(code.paragraph_format.space_after)) == (Inches(0.4), 2)
  run = code.runs[0]
  assert (run.font.name, points(run.font.size), run.font.color.rgb) == ("Consolas", 9.5, RGBColor(71, 85, 105))
  assert paragraphs[2].runs[0].font.name == "Segoe UI"


def shading(cell) -> list[str]:
  return cell._tc.xpath("./w:tcPr/w:shd/@w:fill")


def test_tables_get_a_colored_header_and_alternating_rows():
  doc = render("| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |")
  (table,) = doc.tables
  assert table.alignment == WD_TABLE_ALIGNMENT.CENTER and table.style.name == "Table Grid"
  assert [[c.text for c in row.cells] for row in table.rows] == [["A", "B"], ["1", "2"], ["3", "4"], ["5", "6"]]
  assert [shading(row.cells[0]) for row in table.rows] == [["AA0000"], ["00BB00"], [], ["00BB00"]]
  head = table.rows[0].cells[0].paragraphs[0]
  run = head.runs[-1]
  assert (run.font.bold, points(run.font.size), run.font.color.rgb, run.font.name) == (True, 10, RGBColor(255, 255, 255), "Segoe UI")
  assert (points(head.paragraph_format.space_before), points(head.paragraph_format.space_after)) == (3, 3)
  cell_run = table.rows[1].cells[1].paragraphs[0].runs[-1]
  assert (cell_run.font.bold, points(cell_run.font.size), cell_run.font.color.rgb) == (None, 9.5, RGBColor(51, 65, 85))
  assert cell_run.font.name == "Segoe UI"


def test_table_lines_are_not_written_as_paragraphs():
  doc = render("| A |\n|---|\n| 1 |")
  assert len(doc.tables) == 1 and [p.text for p in doc.paragraphs[2:]] == []


@pytest.mark.parametrize("line", ["| solo apertura", "solo cierre |"])
def test_a_line_with_only_one_pipe_at_an_end_is_not_a_table_row(line):
  doc = render(line)
  assert doc.tables == [] and [p.text for p in doc.paragraphs[2:]] == [line]


def test_a_table_of_only_separator_rows_is_not_written():
  assert render("|---|\n|---|").tables == []


def test_a_table_takes_the_widest_row_as_its_column_count():
  (table,) = render("| A | B | C |\n| 1 |").tables
  assert len(table.columns) == 3
  assert [c.text for c in table.rows[1].cells] == ["1", "", ""]


def test_text_after_a_table_closes_it_and_is_written_after_it():
  doc = render("| A |\n| 1 |\ndespués")
  assert len(doc.tables) == 1 and doc.paragraphs[-1].text == "después"
  assert [child.tag.rsplit("}", 1)[1] for child in doc.element.body][-3:] == ["tbl", "p", "sectPr"]


def test_a_table_interrupted_by_a_code_block_continues_afterwards():
  doc = render("| A |\n| 1 |\n```\ncódigo\n```\n| 2 |")
  (table,) = doc.tables
  assert [row.cells[0].text for row in table.rows] == ["A", "1", "2"]
  assert "código" in [p.text for p in doc.paragraphs]


def test_a_table_at_the_very_end_is_written():
  assert len(render("texto\n| A |\n| 1 |").tables) == 1


def test_nothing_is_added_for_a_table_without_rows():
  doc = Document()
  render_table(doc, [], STYLE)
  assert doc.tables == []


def test_formatted_runs_accept_a_custom_color_and_italic():
  paragraph = Document().add_paragraph()
  add_formatted_runs(paragraph, "a **b** c", italic=True, color=SECONDARY)
  assert [(r.text, r.font.italic, r.font.bold) for r in paragraph.runs] == [("a ", True, None), ("b", None, True), (" c", True, None)]
  assert all(r.font.color.rgb == SECONDARY for r in paragraph.runs)

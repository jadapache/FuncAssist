"""Content-level tests for the markdown -> DOCX builders (inventario, levantamiento, mejoras)."""

from __future__ import annotations

import io

import pytest
from docx import Document

from app.features.inventario.docx_builder import create_inventario_docx
from app.features.levantamiento.docx_builder import create_levantamiento_docx
from app.features.mejoras.docx_builder import create_mejoras_docx

BUILDERS = {
  "inventario": (create_inventario_docx, "Generado a partir de Minutas"),
  "levantamiento": (create_levantamiento_docx, "Documentación Funcional"),
  "mejoras": (create_mejoras_docx, "Generado automáticamente por FuncAssist"),
}

MARKDOWN = """# Encabezado Principal
## Sección Dos
### Subsección Tres

Párrafo normal con **texto en negrita** y resto.

- Viñeta uno
* Viñeta dos con **bold**
1. INTRODUCCION GENERAL
2. paso en minúscula sin mayúscula.
> Nota importante **destacada**

```python
print("hola")
```

| ID | Nombre | Estado |
|----|:------:|--------|
| R1 | Login | OK |
| R2 | Export | Pendiente |
| R3 | Extra |
Texto tras tabla
"""


def _open(data: bytes):
  assert data[:2] == b"PK"
  return Document(io.BytesIO(data))


def _texts(doc):
  return [p.text for p in doc.paragraphs]


@pytest.mark.parametrize("name", list(BUILDERS))
def test_builder_renders_all_markdown_constructs(name):
  builder, subtitle = BUILDERS[name]
  doc = _open(builder(MARKDOWN, title="Mi Documento"))
  texts = _texts(doc)

  assert texts[0] == "MI DOCUMENTO"
  assert texts[0] == texts[0].upper()
  assert doc.paragraphs[0].runs[-1].font.bold is True
  assert subtitle in texts[1]

  for expected in ["Encabezado Principal", "Sección Dos", "Subsección Tres",
                   "Viñeta uno", "Viñeta dos con bold", "1. INTRODUCCION GENERAL",
                   "paso en minúscula sin mayúscula.", "Nota importante destacada",
                   'print("hola")', "Texto tras tabla"]:
    assert expected in texts, (expected, texts)

  # markdown markers stripped
  assert not any(t.startswith("#") for t in texts)
  assert "```python" not in texts

  bold_para = next(p for p in doc.paragraphs if "texto en negrita" in p.text)
  bold_runs = [r for r in bold_para.runs if r.font.bold]
  assert [r.text for r in bold_runs] == ["texto en negrita"]

  bullet = next(p for p in doc.paragraphs if p.text == "Viñeta uno")
  assert bullet.style.name == "List Bullet"
  numbered = next(p for p in doc.paragraphs if p.text == "paso en minúscula sin mayúscula.")
  assert numbered.style.name == "List Number"

  quote = next(p for p in doc.paragraphs if p.text == "Nota importante destacada")
  assert quote.runs[0].font.italic is True

  code = next(p for p in doc.paragraphs if p.text == 'print("hola")')
  assert code.runs[0].font.name == "Consolas"

  # Table: separator row skipped, header + 3 rows, ragged row OK
  assert len(doc.tables) == 1
  table = doc.tables[0]
  assert len(table.rows) == 4
  assert [c.text for c in table.rows[0].cells] == ["ID", "Nombre", "Estado"]
  assert [c.text for c in table.rows[2].cells] == ["R2", "Export", "Pendiente"]
  assert [c.text for c in table.rows[3].cells] == ["R3", "Extra", ""]
  assert table.rows[0].cells[0].paragraphs[0].runs[-1].font.bold is True
  assert "w:shd" in table.rows[0].cells[0]._element.xml




@pytest.mark.parametrize("name", list(BUILDERS))
def test_builder_empty_markdown_uses_default_title(name):
  builder, _ = BUILDERS[name]
  doc = _open(builder(""))
  assert len(doc.paragraphs) == 2
  assert doc.paragraphs[0].text.isupper()
  assert doc.tables == []


def test_inventario_bullet_dot_marker():
  doc = _open(create_inventario_docx("• Punto especial"))
  p = next(p for p in doc.paragraphs if p.text == "Punto especial")
  assert p.style.name == "List Bullet"


def test_levantamiento_checkbox_items():
  doc = _open(create_levantamiento_docx("- [x] Hecho **ya**\n- [ ] Pendiente"))
  done = next(p for p in doc.paragraphs if "Hecho" in p.text)
  todo = next(p for p in doc.paragraphs if "Pendiente" in p.text)
  assert done.text == "[✓] Hecho ya"
  assert todo.text == "[ ] Pendiente"
  assert done.runs[0].font.bold is True
  assert str(done.runs[0].font.color.rgb) == "059669"
  assert str(todo.runs[0].font.color.rgb) == "002777"




def test_mejoras_dot_bullet_is_plain_paragraph():
  doc = _open(create_mejoras_docx("• No es viñeta"))
  p = next(p for p in doc.paragraphs if "No es viñeta" in p.text)
  assert p.style.name != "List Bullet"


# -- each document applies its own style ----------------------------------------------------------------

import io as _io

from docx import Document as _Document
from docx.shared import RGBColor as _RGB

_STYLES = {
  "inventario": (create_inventario_docx, _RGB(0, 39, 119), 18, "Generado a partir de Minutas", "002777", "F1F5F9"),
  "levantamiento": (create_levantamiento_docx, _RGB(0, 39, 119), 18, "Documentación Funcional", "002777", "F8FAFC"),
  "mejoras": (create_mejoras_docx, _RGB(30, 58, 138), 20, "Generado automáticamente", "1E3A8A", "F8FAFC"),
}


@pytest.mark.parametrize("name", list(_STYLES))
def test_each_document_uses_its_own_colors_sizes_and_subtitle(name):
  build, color, title_size, subtitle, header_hex, alt_hex = _STYLES[name]
  doc = _Document(_io.BytesIO(build("| A |\n| 1 |\n| 2 |\n| 3 |", title="Mi Documento")))
  title, sub = doc.paragraphs[:2]
  assert title.text == "MI DOCUMENTO" and title.runs[0].font.color.rgb == color
  assert title.runs[0].font.size.pt == title_size
  assert sub.text.startswith(subtitle)
  (table,) = doc.tables
  fills = [row.cells[0]._tc.xpath("./w:tcPr/w:shd/@w:fill") for row in table.rows]
  assert fills == [[header_hex], [alt_hex], [], [alt_hex]]


def _numbered(build, markdown):
  doc = _Document(_io.BytesIO(build(markdown)))
  return {p.text: p.style.name for p in doc.paragraphs[2:]}


def test_mejoras_keeps_action_steps_and_placeholders_as_list_items():
  styles = _numbered(create_mejoras_docx, "1. Validar el acceso al sistema\n2. {{CAMPO}} DEL FORMULARIO\n3. Alcance General")
  assert styles["Validar el acceso al sistema"] == "List Number"
  assert styles["{{CAMPO}} DEL FORMULARIO"] == "List Number"
  assert styles["3. Alcance General"] == "Normal"


@pytest.mark.parametrize("word", ["Validar", "Verificar", "Confirmar", "Comprobar", "VERIFICAR"])
def test_mejoras_action_words_are_matched_ignoring_case(word):
  assert _numbered(create_mejoras_docx, f"1. {word} los datos de entrada")[f"{word} los datos de entrada"] == "List Number"


@pytest.mark.parametrize("build", [create_inventario_docx, create_levantamiento_docx])
def test_other_documents_turn_the_same_lines_into_titles(build):
  styles = _numbered(build, "1. Validar el acceso al sistema\n2. {{CAMPO}} DEL FORMULARIO")
  assert styles == {"1. Validar el acceso al sistema": "Normal", "2. {{CAMPO}} DEL FORMULARIO": "Normal"}


def test_only_levantamiento_draws_check_boxes_and_mejoras_has_no_dot_bullets():
  assert _Document(_io.BytesIO(create_levantamiento_docx("- [x] hecho"))).paragraphs[2].runs[0].text == "[✓] "
  assert _Document(_io.BytesIO(create_inventario_docx("- [x] hecho"))).paragraphs[2].text == "[x] hecho"
  assert _Document(_io.BytesIO(create_mejoras_docx("• punto"))).paragraphs[2].style.name == "Normal"
  assert _Document(_io.BytesIO(create_inventario_docx("• punto"))).paragraphs[2].style.name == "List Bullet"

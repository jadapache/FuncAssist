"""Content-level tests for the XLSX builders (inventario + mejoras QA matrix)."""

from __future__ import annotations

import io

import openpyxl

from app.features.inventario.xlsx_builder import (
  _extract_tables_from_markdown,
  create_inventario_xlsx,
)
from app.features.mejoras.xlsx_builder import create_qa_matrix_xlsx


def _wb(data: bytes):
  return openpyxl.load_workbook(io.BytesIO(data))


def _rows(ws):
  return [list(r) for r in ws.iter_rows(values_only=True)]


FULL_MD = """# Inventario

| ID | Requerimiento | Prioridad |
|----|---------------|-----------|
| REQ-1 | Login SSO | Alta |
| REQ-2 | Export | Media |

| Stakeholder | Rol |
|---|---|
| Ana | Sponsor |

| Riesgo | Mitigación |
|---|---|
| Retraso | Plan B |
"""


def test_inventario_from_markdown_tables():
  wb = _wb(create_inventario_xlsx(FULL_MD))
  assert wb.sheetnames == ["Requerimientos", "Stakeholders y Riesgos"]
  ws = wb["Requerimientos"]
  rows = _rows(ws)
  assert rows[0] == ["ID", "Requerimiento", "Prioridad"]
  assert rows[1] == ["REQ-1", "Login SSO", "Alta"]
  assert rows[2] == ["REQ-2", "Export", "Media"]
  assert ws["A1"].font.bold and ws["A1"].fill.start_color.rgb.endswith("002777")
  assert ws.freeze_panes == "A2"
  assert ws.column_dimensions["A"].width >= 12

  ws2 = wb["Stakeholders y Riesgos"]
  col_a = [r[0] for r in _rows(ws2)]
  assert col_a[0] == "MATRIZ DE STAKEHOLDERS"
  assert col_a[1:3] == ["Stakeholder", "Ana"]
  assert "MATRIZ DE RIESGOS Y SUPUESTOS" in col_a
  idx = col_a.index("MATRIZ DE RIESGOS Y SUPUESTOS")
  assert _rows(ws2)[idx + 1][:2] == ["Riesgo", "Mitigación"]
  assert _rows(ws2)[idx + 2][:2] == ["Retraso", "Plan B"]


def test_inventario_from_structured_rows():
  rows = [
    {"id": "X-1", "requirement": "Algo", "type": "Funcional", "priority": "Alta",
     "module": "M", "source": "Minuta", "status": "Aprobado"},
    {"id": "X-2", "requirement": "Otro"},
  ]
  wb = _wb(create_inventario_xlsx(rows=rows))
  assert wb.sheetnames == ["Requerimientos"]  # no markdown -> no second sheet
  data = _rows(wb.active)
  assert data[0] == ["ID", "Requerimiento", "Tipo", "Prioridad", "Módulo", "Fuente", "Estado"]
  assert data[1] == ["X-1", "Algo", "Funcional", "Alta", "M", "Minuta", "Aprobado"]
  assert data[2][:2] == ["X-2", "Otro"]
  assert data[2][2:] == [None] * 5  # empty strings saved as empty cells


def test_inventario_default_template_when_no_data():
  wb = _wb(create_inventario_xlsx())
  data = _rows(wb.active)
  assert data[0][1] == "Requerimiento de Alto Nivel"
  assert [r[0] for r in data[1:]] == ["INV-001", "INV-002", "INV-003"]
  assert len(wb.sheetnames) == 1


def test_inventario_markdown_without_tables_still_adds_empty_second_sheet():
  wb = _wb(create_inventario_xlsx("Solo texto sin tablas"))
  assert wb.sheetnames == ["Requerimientos", "Stakeholders y Riesgos"]
  assert _rows(wb.active)[1][0] == "INV-001"
  assert wb["Stakeholders y Riesgos"].max_row == 1
  assert wb["Stakeholders y Riesgos"]["A1"].value is None


def test_inventario_only_risks_table():
  md = "| Impacto | Descripción |\n|---|---|\n| Alto | Caída |"
  wb = _wb(create_inventario_xlsx(md))
  ws2 = wb["Stakeholders y Riesgos"]
  assert ws2["A1"].value == "MATRIZ DE RIESGOS Y SUPUESTOS"
  assert ws2["A3"].value == "Alto"


def test_extract_tables_rules():
  md = "| A |\n|---|\nText\n| H1 | H2 |\n| v1 | v2 |\nend\n| X | Y |\n| 1 | 2 |"
  tables = _extract_tables_from_markdown(md)
  # header-only table (one row) is discarded
  assert tables == [
    {"headers": ["H1", "H2"], "rows": [["v1", "v2"]]},
    {"headers": ["X", "Y"], "rows": [["1", "2"]]},
  ]
  assert _extract_tables_from_markdown("") == []


def test_qa_matrix_default_rows_and_title_truncation():
  long_title = "Matriz de Pruebas QA para el proyecto completo"
  wb = _wb(create_qa_matrix_xlsx(title=long_title))
  ws = wb.active
  assert ws.title == long_title[:31]
  data = _rows(ws)
  assert data[0] == ["ID", "Módulo", "Caso de Prueba", "Precondiciones", "Pasos",
                     "Resultado Esperado", "Prioridad", "Estado"]
  assert data[1][0] == "TC-001"
  assert "Ingresar usuario" in data[1][4]
  assert ws.freeze_panes == "A2"
  assert ws.column_dimensions["E"].width == 40
  assert ws["A2"].alignment.horizontal == "center"
  assert ws["C2"].alignment.horizontal == "left"


def test_qa_matrix_custom_rows():
  rows = [{"id": "T1", "module": "Pagos", "test_case": "Pago ok", "status": "Pass"},
          {"id": "T2"}]
  wb = _wb(create_qa_matrix_xlsx(rows=rows))
  data = _rows(wb.active)
  assert len(data) == 3
  assert data[1][:3] == ["T1", "Pagos", "Pago ok"]
  assert data[1][7] == "Pass"
  assert data[2][0] == "T2"
  assert wb.active["A2"].fill.start_color.rgb.endswith("F0F4FF")


# -- behaviours pinned by mutation testing ---------------------------------------------------------------

LAYOUT_MD = """| ID | Requerimiento | Prioridad |
|---|---|---|
| R1 | Un requerimiento bastante largo para medir | Alta |
| R2 | Corto | Media |
| R3 | Otro | Baja |

| Stakeholder | Rol |
|---|---|
| Ana | Sponsor |
| Beto | Analista |

| Riesgo | Mitigación |
|---|---|
| Retraso | Plan B |
"""


def test_main_sheet_layout_header_height_zebra_and_column_widths():
  ws = _wb(create_inventario_xlsx(LAYOUT_MD))["Requerimientos"]
  assert ws.row_dimensions[1].height == 26
  assert ws["A2"].fill.start_color.rgb.endswith("F0F4FF")
  assert ws["A3"].fill.fill_type is None
  assert ws["A4"].fill.start_color.rgb.endswith("F0F4FF")
  assert ws.column_dimensions["A"].width == 12  # short content never goes below the minimum
  assert ws.column_dimensions["B"].width == len("Un requerimiento bastante largo para medir") + 4
  assert ws.column_dimensions["C"].width == 13


def test_stakeholders_sheet_places_each_section_after_the_previous_rows():
  ws = _wb(create_inventario_xlsx(LAYOUT_MD))["Stakeholders y Riesgos"]
  assert [ws.cell(row=r, column=1).value for r in range(1, 5)] == ["MATRIZ DE STAKEHOLDERS", "Stakeholder", "Ana", "Beto"]
  assert ws.row_dimensions[1].height == 22
  assert ws["A7"].value == "MATRIZ DE RIESGOS Y SUPUESTOS" and ws.row_dimensions[7].height == 22
  assert [ws.cell(row=r, column=1).value for r in (8, 9)] == ["Riesgo", "Retraso"]
  assert ws.column_dimensions["A"].width == len("MATRIZ DE RIESGOS Y SUPUESTOS") + 4
  assert ws.column_dimensions["B"].width == 14


def test_the_generated_file_is_a_complete_xlsx_archive():
  assert create_inventario_xlsx().startswith(b"PK")


def test_only_lines_that_start_and_end_with_a_pipe_are_table_rows():
  md = "| H1 | H2 |\n| v1 | v2 |\n| orphan without closing\ntrailing text |\n| X | Y |\n| 1 | 2 |"
  assert _extract_tables_from_markdown(md) == [
    {"headers": ["H1", "H2"], "rows": [["v1", "v2"]]},
    {"headers": ["X", "Y"], "rows": [["1", "2"]]},
  ]


def test_a_table_that_ends_the_text_is_kept():
  assert _extract_tables_from_markdown("| A |\n| 1 |") == [{"headers": ["A"], "rows": [["1"]]}]
  assert _extract_tables_from_markdown("| A |") == []

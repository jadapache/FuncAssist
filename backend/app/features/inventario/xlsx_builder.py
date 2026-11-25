"""Builder para exportación del Inventario de Requerimientos a formato Excel (.xlsx)."""

from __future__ import annotations

import io
import re
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

PRIMARY_HEX = "002777"       # Corporate Blue
SECONDARY_HEX = "004497"     # Navy Accent
HEADER_FILL_HEX = "002777"
ALT_ROW_HEX = "F0F4FF"
SECTION_FILL_HEX = "E0E7FF"
HEADER_FONT_COLOR = "FFFFFF"


_HEADER_FILL = PatternFill(start_color=HEADER_FILL_HEX, end_color=HEADER_FILL_HEX, fill_type="solid")
_HEADER_FONT = Font(bold=True, color=HEADER_FONT_COLOR, name="Segoe UI", size=11)
_SECTION_FONT = Font(bold=True, color="002777", name="Segoe UI", size=11)
_ALT_FILL = PatternFill(start_color=ALT_ROW_HEX, end_color=ALT_ROW_HEX, fill_type="solid")
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
_BORDER_SIDE = Side(style="thin", color="CBD5E1")
_BORDER = Border(left=_BORDER_SIDE, right=_BORDER_SIDE, top=_BORDER_SIDE, bottom=_BORDER_SIDE)

_ROW_KEYS = ["id", "requirement", "type", "priority", "module", "source", "status"]
_STRUCTURED_HEADERS = ["ID", "Requerimiento", "Tipo", "Prioridad", "Módulo", "Fuente", "Estado"]
_DEFAULT_HEADERS = ["ID", "Requerimiento de Alto Nivel", "Tipo", "Prioridad", "Módulo Relacionado", "Fuente", "Estado"]
_DEFAULT_ROWS = [
  ["INV-001", "Gestión de auditoría y levantamiento temprano", "Funcional", "Alta", "Módulo Funcional", "Minuta Kickoff", "Aprobado"],
  ["INV-002", "Exportación automática a Microsoft Excel (.xlsx)", "Funcional", "Alta", "Exportador", "Especificación", "Aprobado"],
  ["INV-003", "Indexación en base de conocimiento RAG", "Técnico", "Media", "Biblioteca", "Sesión Técnica", "Propuesto"],
]


def _find_table(tables: list[dict[str, Any]], keywords: tuple[str, ...]) -> dict[str, Any] | None:
  """The first table with a header that contains any of the keywords, ignoring case."""
  return next((t for t in tables if any(k in h.lower() for h in t["headers"] for k in keywords)), None)


def _write_header(ws: Any, row: int, headers: list[str]) -> None:
  for col, header in enumerate(headers, start=1):
    cell = ws.cell(row=row, column=col, value=header)
    cell.font = _HEADER_FONT
    cell.fill = _HEADER_FILL
    cell.alignment = _CENTER
    cell.border = _BORDER


def _write_row(ws: Any, row: int, values: list[Any], fill: PatternFill | None = None) -> None:
  for col, value in enumerate(values, start=1):
    cell = ws.cell(row=row, column=col, value=value)
    if fill is not None:
      cell.fill = fill
    cell.alignment = _LEFT
    cell.border = _BORDER
    cell.font = Font(name="Segoe UI", size=10)


def _fit_columns(ws: Any, minimum: int) -> None:
  for index, col in enumerate(ws.columns, start=1):
    longest = max(len(str(cell.value or "")) for cell in col)
    ws.column_dimensions[get_column_letter(index)].width = max(longest + 4, minimum)


def _main_sheet_data(req_table: dict[str, Any] | None, rows: list[dict[str, Any]] | None) -> tuple[list[str], list[list[Any]]]:
  """Headers and data rows of the main sheet: the markdown table, else the structured rows, else the example."""
  if req_table and req_table["rows"]:
    return req_table["headers"], req_table["rows"]
  if rows:
    return _STRUCTURED_HEADERS, [[row.get(key, "") for key in _ROW_KEYS] for row in rows]
  return _DEFAULT_HEADERS, _DEFAULT_ROWS


def _fill_main_sheet(ws: Any, headers: list[str], data: list[list[Any]]) -> None:
  _write_header(ws, 1, headers)
  for row_idx, values in enumerate(data, start=2):
    _write_row(ws, row_idx, values, _ALT_FILL if row_idx % 2 == 0 else PatternFill())
  ws.row_dimensions[1].height = 26
  ws.freeze_panes = "A2"
  _fit_columns(ws, 12)


def _write_section(ws: Any, cursor: int, title: str, table: dict[str, Any]) -> int:
  """A titled table in the stakeholders sheet. Returns the row where the next block can start."""
  ws.cell(row=cursor, column=1, value=title).font = _SECTION_FONT
  ws.row_dimensions[cursor].height = 22
  _write_header(ws, cursor + 1, table["headers"])
  cursor += 2
  for values in table["rows"]:
    _write_row(ws, cursor, values)
    cursor += 1
  return cursor


def _fill_stakeholders_sheet(ws: Any, tables: list[dict[str, Any]]) -> None:
  cursor = 1
  stakeholders = _find_table(tables, ("stakeholder", "rol"))
  if stakeholders and stakeholders["rows"]:
    cursor = _write_section(ws, cursor, "MATRIZ DE STAKEHOLDERS", stakeholders) + 2
  risks = _find_table(tables, ("riesgo", "mitigación", "impacto"))
  if risks and risks["rows"]:
    _write_section(ws, cursor, "MATRIZ DE RIESGOS Y SUPUESTOS", risks)
  _fit_columns(ws, 14)


def create_inventario_xlsx(
  markdown_content: str = "",
  title: str = "Inventario de Requerimientos",
  rows: list[dict[str, Any]] | None = None,
) -> bytes:
  """Construye un archivo .xlsx con el Inventario de Requerimientos y Contexto.

  Puede parsear las tablas y secciones de markdown o usar filas estructuradas.
  """
  wb = openpyxl.Workbook()
  tables = _extract_tables_from_markdown(markdown_content) if markdown_content else []

  main = wb.active
  main.title = "Requerimientos"
  headers, data = _main_sheet_data(_find_table(tables, ("requerimiento", "id")), rows)
  _fill_main_sheet(main, headers, data)

  if _find_table(tables, ("stakeholder", "rol")) or markdown_content:
    _fill_stakeholders_sheet(wb.create_sheet(title="Stakeholders y Riesgos"), tables)

  buffer = io.BytesIO()
  wb.save(buffer)
  buffer.seek(0)
  return buffer.read()


_SEPARATOR_ROW = re.compile(r"^\|[\s\-:|]+\|$")


def _extract_tables_from_markdown(markdown_content: str) -> list[dict[str, Any]]:
  """The markdown tables of the text. A table needs a header and at least one data row."""
  tables: list[dict[str, Any]] = []
  rows: list[list[str]] = []

  def close_table() -> None:
    if len(rows) >= 2:
      tables.append({"headers": rows[0], "rows": rows[1:]})
    rows.clear()

  for line in markdown_content.splitlines():
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
      close_table()
    elif not _SEPARATOR_ROW.match(stripped):
      rows.append([c.strip() for c in stripped.split("|")[1:-1]])
  close_table()
  return tables

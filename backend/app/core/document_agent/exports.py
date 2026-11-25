"""Native Word and Excel files of an artifact, from a corporate template or from the built-in builders."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.core.template_storage import get_template_file_path
from app.features.inventario.xlsx_builder import create_inventario_xlsx
from app.features.levantamiento.docx_builder import create_levantamiento_docx
from app.features.mejoras.docx_builder import create_mejoras_docx
from app.features.mejoras.xlsx_builder import create_qa_matrix_xlsx
from app.services.template_renderer.docx_engine import DocxTemplateRenderer
from app.services.template_renderer.xlsx_engine import XlsxTemplateRenderer

from .payloads import ExportDocxRequest, ExportXlsxRequest


def _resolve_export_data(
    content: str, artifact_data: Optional[Dict[str, Any]], title: str
) -> Dict[str, Any]:
    if artifact_data:
        data = dict(artifact_data)
        data.setdefault("title", title)
        return data

    try:
        parsed = json.loads((content or "").strip())
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        parsed.setdefault("title", title)
        return parsed

    return {"title": title, "content": content, "markdown": content}


def generate_docx_bytes(req: ExportDocxRequest) -> bytes:
    data = _resolve_export_data(req.content, req.artifact_data, req.title)
    if req.template_id:
        tmpl_path = get_template_file_path(req.template_id)
        if tmpl_path and tmpl_path.suffix.lower() == ".docx":
            return DocxTemplateRenderer.render(tmpl_path, data)

    title_lower = req.title.lower()
    if "levantamiento" in title_lower:
        return create_levantamiento_docx(req.text, title=req.title)
    return create_mejoras_docx(req.text, title=req.title)


def generate_xlsx_bytes(req: ExportXlsxRequest) -> bytes:
    data = _resolve_export_data(req.text, req.artifact_data, req.title)
    if req.rows:
        data["rows"] = req.rows

    if req.template_id:
        tmpl_path = get_template_file_path(req.template_id)
        if tmpl_path and tmpl_path.suffix.lower() == ".xlsx":
            return XlsxTemplateRenderer.render(tmpl_path, data)

    title_lower = req.title.lower()
    if "inventario" in title_lower or req.text:
        return create_inventario_xlsx(markdown_content=req.text, title=req.title, rows=req.rows)
    return create_qa_matrix_xlsx(title=req.title, rows=req.rows)


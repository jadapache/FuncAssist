"""
Módulo de almacenamiento, extracción de contenido y administración de plantillas corporativas (.doc, .docx, .xlsx, .md, .txt).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import docx
except ImportError:
    docx = None

from app.core.settings import SETTINGS_DIR, USER_DATA_DIR, ensure_local_dirs

TEMPLATES_DIR = USER_DATA_DIR / "templates"
INDEX_FILE = TEMPLATES_DIR / "templates_index.json"
LEGACY_INDEX_FILE = SETTINGS_DIR / "templates_index.json"

DEFAULT_SYSTEM_TAGS: List[Dict[str, str]] = [
    # AI Content Tags
    {"tag": "NECESIDAD", "label": "Necesidad Identificada", "description": "Generalidad de la oportunidad o requerimiento", "type": "ai"},
    {"tag": "DESCRIPCION", "label": "Descripción del funcionamiento actual", "description": "Descripción detallada del comportamiento actual y pantallas", "type": "ai"},
    {"tag": "REQ_FUNCIONAL", "label": "Requerimiento Funcional", "description": "Comportamiento y reglas de negocio esperadas", "type": "ai"},
    {"tag": "REQ_TECNICO", "label": "Requerimiento Técnico", "description": "Especificaciones técnicas, integraciones y esquema de BD", "type": "ai"},
    {"tag": "BENEFICIO", "label": "Beneficio Esperado", "description": "Beneficios operativos, retorno de inversión y valor", "type": "ai"},
    {"tag": "IMPACTO", "label": "Impacto en Negocio", "description": "Impacto operacional en tiempo, costos y reprocesos", "type": "ai"},
    {"tag": "OBSERVACIONES", "label": "Observaciones Complementarias", "description": "Casos de borde, restricciones y recomendaciones", "type": "ai"},
    {"tag": "FIRMAS", "label": "Firma Participantes", "description": "Tabla de participantes y aprobadores", "type": "ai"},
    {"tag": "AREA", "label": "Área / Sede", "description": "Sedes (HIC / ICV / IMAP) y área solicitante", "type": "ai"},
    {"tag": "MODULO", "label": "Módulo / Funcionalidad", "description": "Módulo o sistema de información impactado", "type": "ai"},
    {"tag": "PRIORIDAD", "label": "Prioridad", "description": "Nivel de prioridad (Alta / Media / Baja)", "type": "ai"},

    # System Function Tags (Computed automatically during export without AI)
    {"tag": "PAGINA", "label": "Número de Página", "description": "Número de página actual (Función automática en Word/PDF)", "type": "function"},
    {"tag": "TOTAL_PAGINAS", "label": "Total de Páginas", "description": "Conteo total de páginas (Función automática en Word/PDF)", "type": "function"},
    {"tag": "FECHA_HOY", "label": "Fecha Actual (DD/MM/AAAA)", "description": "Fecha actual del sistema al generar el archivo", "type": "function"},
    {"tag": "HORA_ACTUAL", "label": "Hora de Generación", "description": "Hora exacta de generación del documento", "type": "function"},
    {"tag": "USUARIO_ACTUAL", "label": "Usuario Solicitante", "description": "Nombre del usuario activo en el sistema", "type": "function"},
]


def ensure_template_dirs() -> None:
    ensure_local_dirs()
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def _load_index() -> List[Dict[str, Any]]:
    ensure_template_dirs()
    if not INDEX_FILE.exists():
        if LEGACY_INDEX_FILE.exists():
            try:
                data = json.loads(LEGACY_INDEX_FILE.read_text(encoding="utf-8"))
                _save_index(data)
                try:
                    LEGACY_INDEX_FILE.unlink()
                except Exception:
                    pass
                return data
            except Exception:
                return []
        return []
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_index(items: List[Dict[str, Any]]) -> None:
    ensure_template_dirs()
    INDEX_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


async def list_templates() -> List[Dict[str, Any]]:
    try:
        from app.db.unit_of_work import AsyncUnitOfWork
        async with AsyncUnitOfWork() as uow:
            items = await uow.corporate_templates.list()
            if items is not None:
                for item in items:
                    if "tags" not in item:
                        item["tags"] = [t["tag"] for t in DEFAULT_SYSTEM_TAGS]
                return items
    except Exception as exc:
        logger.debug(f"DB list_templates fallback to index: {exc}")

    items = _load_index()
    for item in items:
        if "tags" not in item:
            item["tags"] = [t["tag"] for t in DEFAULT_SYSTEM_TAGS]
    return items


async def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    try:
        from app.db.unit_of_work import AsyncUnitOfWork
        async with AsyncUnitOfWork() as uow:
            item = await uow.corporate_templates.get(template_id)
            if item:
                if "tags" not in item:
                    item["tags"] = [t["tag"] for t in DEFAULT_SYSTEM_TAGS]
                return item
    except Exception as exc:
        logger.debug(f"DB get_template fallback to index: {exc}")

    items = _load_index()
    for item in items:
        if item["id"] == template_id:
            if "tags" not in item:
                item["tags"] = [t["tag"] for t in DEFAULT_SYSTEM_TAGS]
            return item
    return None


def get_template_file_path(template_id: str) -> Optional[Path]:
    items = _load_index()
    for item in items:
        if item.get("id") == template_id:
            stored = item.get("stored_filename")
            if stored:
                p = TEMPLATES_DIR / stored
                if p.exists():
                    return p
    return None


_HEADING_PREFIXES = (("Heading 1", "# "), ("Heading 2", "## "), ("Heading 3", "### "))
_TEXT_EXTENSIONS = (".md", ".txt", ".json", ".csv", ".html", ".xml")
DEFAULT_HEADER = "Página {{PAGINA}} | FORMATO CORPORATIVO"
DEFAULT_FOOTER = "Documento Confidencial • Página {{PAGINA}} de {{TOTAL_PAGINAS}}"


def _unique_cell_texts(row: Any) -> List[str]:
    """Text of each cell of a table row; a merged cell is reported once."""
    seen = set()
    cells = []
    for cell in row.cells:
        if cell._tc in seen:
            continue
        seen.add(cell._tc)
        cells.append(cell.text.strip().replace("\n", " "))
    return cells


def _table_rows_markdown(table: Any) -> List[str]:
    """A Word table as markdown rows, with the separator after the first row. Empty rows are left out."""
    rows: List[str] = []
    for index, row in enumerate(table.rows):
        cells = _unique_cell_texts(row)
        if not any(cells):
            continue
        rows.append("| " + " | ".join(cells) + " |")
        if index == 0:
            rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
    return rows


def _story_parts(story: Any) -> List[str]:
    """The tables and the paragraphs of a header or footer; a paragraph already inside a table is skipped."""
    parts: List[str] = []
    for table in story.tables:
        rows = _table_rows_markdown(table)
        if rows:
            parts.append("\n".join(rows))
    for paragraph in story.paragraphs:
        text = paragraph.text.strip()
        if text and not any(text in part for part in parts):
            parts.append(text)
    return parts


def _header_footer_parts(doc: Any) -> tuple[List[str], List[str]]:
    if not doc.sections:
        return [], []
    section = doc.sections[0]
    header = _story_parts(section.header) if section.header else []
    footer = _story_parts(section.footer) if section.footer else []
    return header, footer


def _paragraph_line(paragraph: Any) -> Optional[str]:
    text = paragraph.text.strip()
    if not text:
        return None
    style_name = paragraph.style.name if paragraph.style else ""
    for marker, prefix in _HEADING_PREFIXES:
        if marker in style_name:
            return prefix + text
    return text


def _body_lines(doc: Any) -> List[str]:
    """Paragraphs and tables of the body, in document order."""
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    lines: List[str] = []
    for child in doc.element.body:
        if isinstance(child, CT_P):
            line = _paragraph_line(Paragraph(child, doc))
            if line:
                lines.append(line)
        elif isinstance(child, CT_Tbl):
            rows = _table_rows_markdown(Table(child, doc))
            if rows:
                lines.append("\n" + "\n".join(rows) + "\n")
    if lines:
        return lines
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]


def extract_docx_structure(file_path: Path) -> Dict[str, Any]:
    if docx is None:
        return {"content": "Librería python-docx no disponible.", "header": "", "footer": ""}

    try:
        doc = docx.Document(file_path)
        header_parts, footer_parts = _header_footer_parts(doc)
        return {
            "content": "\n\n".join(_body_lines(doc)),
            "header": "\n".join(header_parts) if header_parts else DEFAULT_HEADER,
            "footer": "\n".join(footer_parts) if footer_parts else DEFAULT_FOOTER,
        }
    except Exception as e:
        return {"content": f"Error al extraer estructura .docx: {e}", "header": "", "footer": ""}


def _read_text_file(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return file_path.read_text(encoding="latin-1")
        except Exception as e:
            return f"Error al leer el archivo de texto: {e}"


def _xlsx_text(file_path: Path) -> str:
    """The shared strings of a workbook, one per line."""
    try:
        lines = []
        with zipfile.ZipFile(file_path, "r") as z:
            if "xl/sharedStrings.xml" in z.namelist():
                content = z.read("xl/sharedStrings.xml").decode("utf-8", errors="ignore")
                lines = [s for s in re.findall(r"<t[^>]*>(.*?)</t>", content) if s.strip()]
        return "\n".join(lines) if lines else "Archivo Excel (.xlsx) cargado exitosamente."
    except Exception:
        return "Archivo de Hoja de Cálculo Excel (.xlsx) listo para estructurar celdas y etiquetas."


def _binary_text(file_path: Path) -> Optional[str]:
    """The printable strings of a binary file (.doc and the like), or None when there are none."""
    try:
        printable = re.findall(rb"[\x20-\x7E\x80-\xFF]{4,}", file_path.read_bytes())
        decoded = [s.decode("utf-8", errors="ignore") for s in printable if len(s.strip()) > 3]
    except Exception:
        return None
    return "\n".join(decoded[:200]) if decoded else None


def extract_template_content(stored_filename: str) -> str:
    file_path = TEMPLATES_DIR / stored_filename
    if not file_path.exists():
        return "El archivo de la plantilla no se encuentra en el servidor."

    ext = file_path.suffix.lower()
    if ext in _TEXT_EXTENSIONS:
        return _read_text_file(file_path)
    if ext == ".docx":
        return extract_docx_structure(file_path)["content"]
    if ext == ".xlsx":
        return _xlsx_text(file_path)
    return _binary_text(file_path) or f"Plantilla binaria ({ext}) almacenada correctamente."


def detect_tags(content: str) -> List[str]:
    found = set()
    matches = re.findall(r"\{\{\s*([A-Za-z0-9_\-\.]+)\s*\}\}|\[\[\s*([A-Za-z0-9_\-\.]+)\s*\]\]", content)
    for m in matches:
        tag = m[0] or m[1]
        if tag:
            found.add(tag.upper())
    return sorted(list(found))


async def save_template_file(
    filename: str, file_bytes: bytes, title: str = "", module: str = "general"
) -> Dict[str, Any]:
    import asyncio
    ensure_template_dirs()
    template_id = str(uuid.uuid4())
    ext = Path(filename).suffix.lower()
    stored_filename = f"{template_id}{ext}"
    file_path = TEMPLATES_DIR / stored_filename
    await asyncio.to_thread(file_path.write_bytes, file_bytes)

    # Initial content extraction & tag detection
    content_sample = await asyncio.to_thread(extract_template_content, stored_filename)
    detected = detect_tags(content_sample)
    default_tags = [t["tag"] for t in DEFAULT_SYSTEM_TAGS]
    merged_tags = sorted(list(set(default_tags + detected)))

    display_title = title.strip() or Path(filename).stem
    module_name = module or "general"
    item = {
        "id": template_id,
        "title": display_title,
        "filename": filename,
        "stored_filename": stored_filename,
        "file_type": ext.lstrip("."),
        "file_size": len(file_bytes),
        "module": module_name,
        "tags": merged_tags,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }

    items = _load_index()
    items.append(item)
    _save_index(items)

    try:
        from app.db.unit_of_work import AsyncUnitOfWork
        async with AsyncUnitOfWork() as uow:
            await uow.corporate_templates.upsert(item)
            await uow.commit()
    except Exception as exc:
        logger.debug(f"DB save_template_file error: {exc}")

    return item


def _apply_metadata(item: Dict[str, Any], title: Optional[str], module: Optional[str], tags: Optional[List[str]]) -> None:
    if title is not None and title.strip():
        item["title"] = title.strip()
    if module is not None and module.strip():
        item["module"] = module.strip()
    if tags is not None:
        item["tags"] = sorted(list(set(tags)))


async def _store_custom_content(item: Dict[str, Any], content: str) -> None:
    """Keep the edited content: text templates are rewritten in place, the others get a sidecar file."""
    import asyncio

    item["custom_content"] = content
    file_path = TEMPLATES_DIR / item.get("stored_filename", "")
    if file_path.suffix.lower() in _TEXT_EXTENSIONS:
        target = file_path
    else:
        target = TEMPLATES_DIR / f"{item['stored_filename']}.content.md"
    await asyncio.to_thread(target.write_text, content, encoding="utf-8")
    item["file_size"] = len(content.encode("utf-8"))


async def update_template_metadata(
    template_id: str,
    title: Optional[str] = None,
    module: Optional[str] = None,
    tags: Optional[List[str]] = None,
    content: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    items = _load_index()
    for item in items:
        if item["id"] != template_id:
            continue
        _apply_metadata(item, title, module, tags)
        if content is not None:
            await _store_custom_content(item, content)
        _save_index(items)

        try:
            from app.db.unit_of_work import AsyncUnitOfWork
            async with AsyncUnitOfWork() as uow:
                await uow.corporate_templates.upsert(item)
                await uow.commit()
        except Exception as exc:
            logger.debug(f"DB update_template error: {exc}")

        return item
    return None


async def _template_body(item: Dict[str, Any], stored_name: str, parsed: Optional[Dict[str, Any]]) -> str:
    """The text of a template: what the user edited, else its sidecar, else what the file itself holds."""
    import asyncio

    if item.get("custom_content") is not None:
        return item["custom_content"]
    sidecar = TEMPLATES_DIR / f"{stored_name}.content.md"
    if sidecar.exists():
        return await asyncio.to_thread(sidecar.read_text, encoding="utf-8")
    if parsed is not None:
        return parsed["content"]
    return await asyncio.to_thread(extract_template_content, stored_name)


async def get_template_detail(template_id: str) -> Optional[Dict[str, Any]]:
    import asyncio
    item = await get_template(template_id)
    if not item:
        return None

    stored_name = item.get("stored_filename", "")
    file_path = TEMPLATES_DIR / stored_name

    is_docx = file_path.suffix.lower() == ".docx"
    parsed = await asyncio.to_thread(extract_docx_structure, file_path) if is_docx else None
    header_text = parsed["header"] if parsed else ""
    footer_text = parsed["footer"] if parsed else ""
    content = await _template_body(item, stored_name, parsed)

    detected = detect_tags(f"{header_text}\n{content}\n{footer_text}")

    return {
        "template": item,
        "content": content,
        "header_content": header_text,
        "footer_content": footer_text,
        "detected_tags": detected,
        "system_tags": DEFAULT_SYSTEM_TAGS,
    }


async def delete_template(template_id: str) -> bool:
    import asyncio
    items = _load_index()
    target = None
    new_items = []
    for item in items:
        if item["id"] == template_id:
            target = item
        else:
            new_items.append(item)

    if target:
        _save_index(new_items)
        file_path = TEMPLATES_DIR / target.get("stored_filename", "")
        if file_path.exists():
            try:
                await asyncio.to_thread(file_path.unlink)
            except Exception:
                pass

        try:
            from app.db.unit_of_work import AsyncUnitOfWork
            async with AsyncUnitOfWork() as uow:
                await uow.corporate_templates.delete(template_id)
                await uow.commit()
        except Exception as exc:
            logger.debug(f"DB delete_template error: {exc}")

        return True
    return False



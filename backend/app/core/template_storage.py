"""
Módulo de almacenamiento, extracción de contenido y administración de plantillas corporativas (.doc, .docx, .xlsx, .md, .txt).
"""

from __future__ import annotations

import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def list_templates() -> List[Dict[str, Any]]:
    items = _load_index()
    for item in items:
        if "tags" not in item:
            item["tags"] = [t["tag"] for t in DEFAULT_SYSTEM_TAGS]
    return items


def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    items = _load_index()
    for item in items:
        if item["id"] == template_id:
            if "tags" not in item:
                item["tags"] = [t["tag"] for t in DEFAULT_SYSTEM_TAGS]
            return item
    return None


def extract_docx_structure(file_path: Path) -> Dict[str, Any]:
    if docx is None:
        return {"content": "Librería python-docx no disponible.", "header": "", "footer": ""}

    try:
        doc = docx.Document(file_path)
        header_parts = []
        footer_parts = []

        if doc.sections:
            sec = doc.sections[0]
            if sec.header:
                for t in sec.header.tables:
                    table_md_rows = []
                    for r_idx, row in enumerate(t.rows):
                        cells = []
                        seen_tc = set()
                        for c in row.cells:
                            if c._tc not in seen_tc:
                                seen_tc.add(c._tc)
                                cells.append(c.text.strip().replace("\n", " "))
                        if any(cells):
                            table_md_rows.append("| " + " | ".join(cells) + " |")
                            if r_idx == 0:
                                table_md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
                    if table_md_rows:
                        header_parts.append("\n".join(table_md_rows))

                for p in sec.header.paragraphs:
                    txt = p.text.strip()
                    if txt and not any(txt in hp for hp in header_parts):
                        header_parts.append(txt)

            if sec.footer:
                for t in sec.footer.tables:
                    table_md_rows = []
                    for r_idx, row in enumerate(t.rows):
                        cells = []
                        seen_tc = set()
                        for c in row.cells:
                            if c._tc not in seen_tc:
                                seen_tc.add(c._tc)
                                cells.append(c.text.strip().replace("\n", " "))
                        if any(cells):
                            table_md_rows.append("| " + " | ".join(cells) + " |")
                            if r_idx == 0:
                                table_md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
                    if table_md_rows:
                        footer_parts.append("\n".join(table_md_rows))

                for p in sec.footer.paragraphs:
                    txt = p.text.strip()
                    if txt and not any(txt in fp for fp in footer_parts):
                        footer_parts.append(txt)

        # Parse body elements preserving exact order (paragraphs and tables)
        body_lines = []
        from docx.oxml.text.paragraph import CT_P
        from docx.oxml.table import CT_Tbl
        from docx.text.paragraph import Paragraph
        from docx.table import Table

        for child in doc.element.body:
            if isinstance(child, CT_P):
                p = Paragraph(child, doc)
                text = p.text.strip()
                if text:
                    style_name = p.style.name if p.style else ""
                    if "Heading 1" in style_name:
                        body_lines.append(f"# {text}")
                    elif "Heading 2" in style_name:
                        body_lines.append(f"## {text}")
                    elif "Heading 3" in style_name:
                        body_lines.append(f"### {text}")
                    else:
                        body_lines.append(text)
            elif isinstance(child, CT_Tbl):
                t = Table(child, doc)
                table_md_rows = []
                for r_idx, row in enumerate(t.rows):
                    cells = []
                    seen_tc = set()
                    for c in row.cells:
                        if c._tc not in seen_tc:
                            seen_tc.add(c._tc)
                            cells.append(c.text.strip().replace("\n", " "))
                    if any(cells):
                        table_md_rows.append("| " + " | ".join(cells) + " |")
                        if r_idx == 0:
                            table_md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
                if table_md_rows:
                    body_lines.append("\n" + "\n".join(table_md_rows) + "\n")

        # Fallback if body_lines empty
        if not body_lines:
            for p in doc.paragraphs:
                if p.text.strip():
                    body_lines.append(p.text.strip())

        return {
            "content": "\n\n".join(body_lines),
            "header": "\n".join(header_parts) if header_parts else "Página {{PAGINA}} | FORMATO CORPORATIVO",
            "footer": "\n".join(footer_parts) if footer_parts else "Documento Confidencial • Página {{PAGINA}} de {{TOTAL_PAGINAS}}",
        }
    except Exception as e:
        return {"content": f"Error al extraer estructura .docx: {e}", "header": "", "footer": ""}


def extract_template_content(stored_filename: str) -> str:
    file_path = TEMPLATES_DIR / stored_filename
    if not file_path.exists():
        return "El archivo de la plantilla no se encuentra en el servidor."

    ext = file_path.suffix.lower()

    # Plain text formats
    if ext in [".md", ".txt", ".json", ".csv", ".html", ".xml"]:
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                return file_path.read_text(encoding="latin-1")
            except Exception as e:
                return f"Error al leer el archivo de texto: {e}"

    # DOCX format with rich table/header extraction
    if ext == ".docx":
        res = extract_docx_structure(file_path)
        return res["content"]

    # XLSX format (Extract text from sharedStrings or sheet XML)
    if ext == ".xlsx":
        try:
            lines = []
            with zipfile.ZipFile(file_path, "r") as z:
                if "xl/sharedStrings.xml" in z.namelist():
                    content = z.read("xl/sharedStrings.xml").decode("utf-8", errors="ignore")
                    strings = re.findall(r"<t[^>]*>(.*?)</t>", content)
                    lines.extend([s for s in strings if s.strip()])
            return "\n".join(lines) if lines else "Archivo Excel (.xlsx) cargado exitosamente."
        except Exception:
            return "Archivo de Hoja de Cálculo Excel (.xlsx) listo para estructurar celdas y etiquetas."

    # Binary fallback / DOC format
    try:
        raw_bytes = file_path.read_bytes()
        printable_strings = re.findall(rb"[\x20-\x7E\x80-\xFF]{4,}", raw_bytes)
        decoded = [s.decode("utf-8", errors="ignore") for s in printable_strings if len(s.strip()) > 3]
        if decoded:
            return "\n".join(decoded[:200])
    except Exception:
        pass

    return f"Plantilla binaria ({ext}) almacenada correctamente."


def detect_tags(content: str) -> List[str]:
    found = set()
    matches = re.findall(r"\{\{\s*([A-Za-z0-9_\-\.]+)\s*\}\}|\[\[\s*([A-Za-z0-9_\-\.]+)\s*\]\]", content)
    for m in matches:
        tag = m[0] or m[1]
        if tag:
            found.add(tag.upper())
    return sorted(list(found))


def save_template_file(
    filename: str, file_bytes: bytes, title: str = "", module: str = "general"
) -> Dict[str, Any]:
    ensure_template_dirs()
    template_id = str(uuid.uuid4())
    ext = Path(filename).suffix.lower()
    stored_filename = f"{template_id}{ext}"
    file_path = TEMPLATES_DIR / stored_filename
    file_path.write_bytes(file_bytes)

    # Initial content extraction & tag detection
    content_sample = extract_template_content(stored_filename)
    detected = detect_tags(content_sample)
    default_tags = [t["tag"] for t in DEFAULT_SYSTEM_TAGS]
    merged_tags = sorted(list(set(default_tags + detected)))

    item = {
        "id": template_id,
        "title": title.strip() or Path(filename).stem,
        "filename": filename,
        "stored_filename": stored_filename,
        "file_type": ext.lstrip("."),
        "file_size": len(file_bytes),
        "module": module or "general",
        "tags": merged_tags,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),

    }

    items = _load_index()
    items.append(item)
    _save_index(items)
    return item


def update_template_metadata(
    template_id: str,
    title: Optional[str] = None,
    module: Optional[str] = None,
    tags: Optional[List[str]] = None,
    content: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    items = _load_index()
    for item in items:
        if item["id"] == template_id:
            if title is not None and title.strip():
                item["title"] = title.strip()
            if module is not None and module.strip():
                item["module"] = module.strip()
            if tags is not None:
                item["tags"] = sorted(list(set(tags)))

            if content is not None:
                item["custom_content"] = content
                file_path = TEMPLATES_DIR / item.get("stored_filename", "")
                ext = file_path.suffix.lower()
                if ext in [".md", ".txt", ".json", ".html", ".xml", ".csv"]:
                    file_path.write_text(content, encoding="utf-8")
                else:
                    sidecar = TEMPLATES_DIR / f"{item['stored_filename']}.content.md"
                    sidecar.write_text(content, encoding="utf-8")
                item["file_size"] = len(content.encode("utf-8"))

            _save_index(items)
            return item
    return None


def get_template_detail(template_id: str) -> Optional[Dict[str, Any]]:
    item = get_template(template_id)
    if not item:
        return None

    stored_name = item.get("stored_filename", "")
    file_path = TEMPLATES_DIR / stored_name

    header_text = ""
    footer_text = ""

    if "custom_content" in item:
        content = item["custom_content"]
    else:
        sidecar = TEMPLATES_DIR / f"{stored_name}.content.md"
        if sidecar.exists():
            content = sidecar.read_text(encoding="utf-8")
        elif file_path.suffix.lower() == ".docx":
            parsed = extract_docx_structure(file_path)
            content = parsed["content"]
            header_text = parsed["header"]
            footer_text = parsed["footer"]
        else:
            content = extract_template_content(stored_name)

    if file_path.suffix.lower() == ".docx" and not header_text:
        parsed = extract_docx_structure(file_path)
        header_text = parsed.get("header", "")
        footer_text = parsed.get("footer", "")

    full_text_for_tags = f"{header_text}\n{content}\n{footer_text}"
    detected = detect_tags(full_text_for_tags)

    return {
        "template": item,
        "content": content,
        "header_content": header_text,
        "footer_content": footer_text,
        "detected_tags": detected,
        "system_tags": DEFAULT_SYSTEM_TAGS,
    }


def delete_template(template_id: str) -> bool:
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
                file_path.unlink()
            except Exception:
                pass
        return True
    return False



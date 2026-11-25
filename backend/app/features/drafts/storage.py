from __future__ import annotations

import json
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

from app.core.settings import (
  GENERATED_DIR,
  USER_DRAFTS_DIR,
  ensure_local_dirs,
)

logger = logging.getLogger(__name__)

SPEC_MAP = {
  "levantamiento": "Levantamiento",
  "levantamiento_requerimientos": "Levantamiento",
  "requerimientos": "Levantamiento",
  "inventario": "Inventario",
  "inventario_requerimientos": "Inventario",
  "chat": "Mejoras",
  "mejoras": "Mejoras",
  "analisis_qa": "Mejoras",
  "qa_improvements": "Mejoras",
  "qa_analysis": "Mejoras",
}

VALID_SPECS = ["Mejoras", "Levantamiento", "Inventario"]


def normalize_specification(spec: Optional[str]) -> str:
  if not spec:
    return "Levantamiento"
  clean = str(spec).strip().lower()
  if clean in SPEC_MAP:
    return SPEC_MAP[clean]
  for valid in VALID_SPECS:
    if valid.lower() == clean:
      return valid
  return "Levantamiento"


def sanitize_folder_name(name: str) -> str:
  safe = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
  safe = re.sub(r"\s+", "_", safe)
  return safe[:60] if safe else "Borrador"


def ensure_draft_dirs() -> None:
  ensure_local_dirs()
  GENERATED_DIR.mkdir(parents=True, exist_ok=True)
  USER_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
  for spec in VALID_SPECS:
    (USER_DRAFTS_DIR / spec).mkdir(exist_ok=True)


def _draft_folders() -> Iterator[Path]:
  """Every folder inside a specification folder; loose files at either level are ignored."""
  for spec_dir in USER_DRAFTS_DIR.iterdir():
    if spec_dir.is_dir():
      yield from (draft_dir for draft_dir in spec_dir.iterdir() if draft_dir.is_dir())


def _read_metadata(draft_dir: Path) -> Optional[Dict[str, Any]]:
  """The draft's metadata with its folder path, or None when the file is missing, unreadable or has no id."""
  meta_file = draft_dir / "metadata.json"
  if not meta_file.exists():
    return None
  try:
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
  except Exception:
    return None
  if not isinstance(meta, dict) or "id" not in meta:
    return None
  meta["folder_path"] = str(draft_dir)
  return meta


def _scan_drafts_from_disk() -> List[Dict[str, Any]]:
  """Scans metadata.json files directly from user documents Borradores folder."""
  ensure_draft_dirs()
  items = [meta for meta in map(_read_metadata, _draft_folders()) if meta]
  items.sort(key=lambda x: x.get("last_interaction", x.get("updated_at", "")), reverse=True)
  return items


def _format_chat_as_markdown(title: str, spec: str, messages: List[Dict[str, Any]]) -> str:
  lines = [
    f"# Historial de Sesión - {title}",
    f"**Especificación:** {spec}",
    f"**Fecha:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
    "",
    "---",
    "",
  ]
  for msg in messages:
    role = msg.get("role", "user")
    role_label = "Usuario" if role == "user" else "Asistente QA"
    ts = msg.get("timestamp", "")
    lines.append(f"### {role_label} ({ts})")
    lines.append(msg.get("content", "").strip())
    lines.append("")

  return "\n".join(lines)


def _build_docx(content: str, title: str) -> bytes:
  from app.features.levantamiento.docx_builder import create_levantamiento_docx
  return create_levantamiento_docx(content, title=title)


def _build_xlsx(content: str, title: str) -> bytes:
  from app.features.inventario.xlsx_builder import create_inventario_xlsx
  return create_inventario_xlsx(content, title=title)


_BINARY_BUILDERS: Dict[str, Callable[[str, str], bytes]] = {"docx": _build_docx, "xlsx": _build_xlsx}


def _save_artifact(draft_folder: Path, art: Dict[str, Any]) -> Dict[str, Any]:
  """Writes the markdown source of an artifact and, for docx and xlsx, the binary file next to it."""
  art_title = art.get("title") or "Documento"
  art_ext = (art.get("extension") or "docx").lower()
  art_content = art.get("content", "")
  safe_title = sanitize_folder_name(art_title)

  md_path = draft_folder / f"{safe_title}.md"
  md_path.write_text(art_content, encoding="utf-8")

  target_file_path = str(md_path)
  build = _BINARY_BUILDERS.get(art_ext)
  if build:
    try:
      binary_path = draft_folder / f"{safe_title}.{art_ext}"
      binary_path.write_bytes(build(art_content, art_title))
      target_file_path = str(binary_path)
    except Exception as exc:
      logger.warning(f"Could not build {art_ext.upper()} for {art_title}: {exc}")

  return {
    "id": art.get("id", str(uuid.uuid4())),
    "title": art_title,
    "extension": art_ext,
    "path": target_file_path,
    "md_path": str(md_path),
    "created_at": art.get("createdAt", ""),
    "updated_at": art.get("updatedAt", ""),
  }


def _save_standalone_document(draft_folder: Path, safe_name: str, title: str, content: str) -> Dict[str, Any]:
  doc_path = draft_folder / f"{safe_name}.md"
  doc_path.write_text(content, encoding="utf-8")
  return {
    "id": str(uuid.uuid4()),
    "title": title,
    "extension": "md",
    "path": str(doc_path),
    "md_path": str(doc_path),
  }


def save_draft_session(session_data: Dict[str, Any]) -> Dict[str, Any]:
  """Persist a chat session and its generated artifacts into Documents/FuncAssist/Borradores/{Specification}/."""
  ensure_draft_dirs()
  session_id = session_data.get("id") or str(uuid.uuid4())
  title = session_data.get("name") or session_data.get("title") or "Borrador"
  spec = normalize_specification(session_data.get("specification") or session_data.get("feature_slug"))
  last_interaction = session_data.get("lastInteraction") or session_data.get("last_interaction") or datetime.now(timezone.utc).isoformat()
  messages = session_data.get("messages", [])
  artifacts = session_data.get("artifacts", [])
  doc_content = session_data.get("documentContent", "")

  safe_name = sanitize_folder_name(title)
  draft_folder = USER_DRAFTS_DIR / spec / f"{safe_name}_{session_id[:8]}"
  draft_folder.mkdir(parents=True, exist_ok=True)

  chat = {
    "id": session_id,
    "title": title,
    "specification": spec,
    "last_interaction": last_interaction,
    "messages": messages,
    "documentContent": doc_content,
  }
  (draft_folder / "chat.json").write_text(json.dumps(chat, indent=2, ensure_ascii=False), encoding="utf-8")
  (draft_folder / "chat.md").write_text(_format_chat_as_markdown(title, spec, messages), encoding="utf-8")

  if artifacts:
    saved_artifact_meta = [_save_artifact(draft_folder, art) for art in artifacts]
  elif doc_content:
    saved_artifact_meta = [_save_standalone_document(draft_folder, safe_name, title, doc_content)]
  else:
    saved_artifact_meta = []

  meta_entry = {
    "id": session_id,
    "user_id": session_data.get("user_id"),
    "title": title,
    "specification": spec,
    "last_interaction": last_interaction,
    "folder_path": str(draft_folder),
    "message_count": len(messages),
    "artifact_count": len(saved_artifact_meta),
    "artifacts": saved_artifact_meta,
    "updated_at": datetime.now(timezone.utc).isoformat(),
  }
  (draft_folder / "metadata.json").write_text(json.dumps(meta_entry, indent=2, ensure_ascii=False), encoding="utf-8")

  return meta_entry


def list_generated_drafts(
  specification: Optional[str] = None, user_id: Optional[str] = None
) -> List[Dict[str, Any]]:
  items = _scan_drafts_from_disk()
  if user_id:
    items = [i for i in items if not i.get("user_id") or i.get("user_id") == user_id]
  if specification:
    norm = normalize_specification(specification)
    items = [i for i in items if i.get("specification") == norm]
  return items


def get_generated_draft(draft_id: str) -> Optional[Dict[str, Any]]:
  items = _scan_drafts_from_disk()
  for item in items:
    if item.get("id") == draft_id:
      folder_path = Path(item["folder_path"])
      chat_json = folder_path / "chat.json"
      if chat_json.exists():
        try:
          detail = json.loads(chat_json.read_text(encoding="utf-8"))
          item["details"] = detail
        except Exception:
          pass
      return item
  return None


def delete_generated_draft(draft_id: str) -> bool:
  items = _scan_drafts_from_disk()
  target = next((item for item in items if item.get("id") == draft_id), None)
  if not target:
    return False
  shutil.rmtree(target["folder_path"], ignore_errors=True)
  return True

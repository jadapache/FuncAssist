from __future__ import annotations

import json
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.settings import (
  GENERATED_DIR,
  GENERATED_INDEX_FILE,
  USER_DATA_DIR,
  USER_DOCUMENTS_DIR,
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
    (USER_DRAFTS_DIR / spec).mkdir(parents=True, exist_ok=True)


def _scan_drafts_from_disk() -> List[Dict[str, Any]]:
  """Scans metadata.json files directly from user documents Borradores folder."""
  ensure_draft_dirs()
  items: List[Dict[str, Any]] = []
  if not USER_DRAFTS_DIR.exists():
    return items

  for spec_dir in USER_DRAFTS_DIR.iterdir():
    if not spec_dir.is_dir():
      continue
    for draft_dir in spec_dir.iterdir():
      if not draft_dir.is_dir():
        continue
      meta_file = draft_dir / "metadata.json"
      if meta_file.exists():
        try:
          meta = json.loads(meta_file.read_text(encoding="utf-8"))
          if isinstance(meta, dict) and "id" in meta:
            meta["folder_path"] = str(draft_dir)
            items.append(meta)
        except Exception:
          pass

  items.sort(key=lambda x: x.get("last_interaction", x.get("updated_at", "")), reverse=True)
  return items


def _load_generated_index() -> List[Dict[str, Any]]:
  return _scan_drafts_from_disk()


def _save_generated_index(items: List[Dict[str, Any]]) -> None:
  # Deprecated: index files in AppData are no longer written
  if GENERATED_INDEX_FILE.exists():
    try:
      GENERATED_INDEX_FILE.unlink()
    except Exception:
      pass


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
    role_label = "👤 Usuario" if role == "user" else "🤖 Asistente QA"
    ts = msg.get("timestamp", "")
    lines.append(f"### {role_label} ({ts})")
    lines.append(msg.get("content", "").strip())
    lines.append("")

  return "\n".join(lines)


def save_draft_session(session_data: Dict[str, Any]) -> Dict[str, Any]:
  """
  Persist a chat session and its generated artifacts into Documents/QA MGMT/Borradores/{Specification}/
  and register it in the OS User Data Generated/_index.json.
  """
  ensure_draft_dirs()
  session_id = session_data.get("id") or str(uuid.uuid4())
  title = session_data.get("name") or session_data.get("title") or "Borrador"
  spec = normalize_specification(session_data.get("specification") or session_data.get("feature_slug"))
  last_interaction = session_data.get("lastInteraction") or session_data.get("last_interaction") or datetime.now(timezone.utc).isoformat()
  messages = session_data.get("messages", [])
  artifacts = session_data.get("artifacts", [])
  doc_content = session_data.get("documentContent", "")

  safe_name = sanitize_folder_name(title)
  folder_name = f"{safe_name}_{session_id[:8]}"
  draft_folder = USER_DRAFTS_DIR / spec / folder_name
  draft_folder.mkdir(parents=True, exist_ok=True)

  # 1. Save chat.json and human-readable chat.md
  chat_json_path = draft_folder / "chat.json"
  chat_json_path.write_text(json.dumps({
    "id": session_id,
    "title": title,
    "specification": spec,
    "last_interaction": last_interaction,
    "messages": messages,
    "documentContent": doc_content,
  }, indent=2, ensure_ascii=False), encoding="utf-8")

  chat_md_path = draft_folder / "chat.md"
  chat_md_content = _format_chat_as_markdown(title, spec, messages)
  chat_md_path.write_text(chat_md_content, encoding="utf-8")

  # 2. Save document/artifacts
  saved_artifact_meta = []
  if artifacts:
    for art in artifacts:
      art_title = art.get("title") or "Documento"
      art_ext = (art.get("extension") or "docx").lower()
      art_content = art.get("content", "")
      safe_art_title = sanitize_folder_name(art_title)

      # Write markdown source
      md_path = draft_folder / f"{safe_art_title}.md"
      md_path.write_text(art_content, encoding="utf-8")

      target_file_path = str(md_path)
      # If binary format like docx or xlsx, generate binary file alongside .md
      if art_ext == "docx":
        try:
          from app.features.levantamiento.docx_builder import create_levantamiento_docx
          docx_bytes = create_levantamiento_docx(art_content, title=art_title)
          docx_path = draft_folder / f"{safe_art_title}.docx"
          docx_path.write_bytes(docx_bytes)
          target_file_path = str(docx_path)
        except Exception as exc:
          logger.warning(f"Could not build DOCX for {art_title}: {exc}")
      elif art_ext == "xlsx":
        try:
          from app.features.inventario.xlsx_builder import create_inventario_xlsx
          xlsx_bytes = create_inventario_xlsx(art_content, title=art_title)
          xlsx_path = draft_folder / f"{safe_art_title}.xlsx"
          xlsx_path.write_bytes(xlsx_bytes)
          target_file_path = str(xlsx_path)
        except Exception as exc:
          logger.warning(f"Could not build XLSX for {art_title}: {exc}")

      saved_artifact_meta.append({
        "id": art.get("id", str(uuid.uuid4())),
        "title": art_title,
        "extension": art_ext,
        "path": target_file_path,
        "md_path": str(md_path),
        "created_at": art.get("createdAt", ""),
        "updated_at": art.get("updatedAt", ""),
      })
  elif doc_content:
    # Save standalone documentContent
    doc_path = draft_folder / f"{safe_name}.md"
    doc_path.write_text(doc_content, encoding="utf-8")
    saved_artifact_meta.append({
      "id": str(uuid.uuid4()),
      "title": title,
      "extension": "md",
      "path": str(doc_path),
      "md_path": str(doc_path),
    })

  # 3. Save metadata.json in the draft subfolder
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


def _load_index_with_fs_sync() -> List[Dict[str, Any]]:
  return _scan_drafts_from_disk()


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
  if target:
    folder_str = target.get("folder_path")
    if folder_str:
      folder = Path(folder_str)
      if folder.exists() and folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
    return True
  return False

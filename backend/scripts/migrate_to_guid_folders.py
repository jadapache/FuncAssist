"""
Migrates existing flat transcription JSONs and media to GUID subfolder layout.
Run once: python -m backend.scripts.migrate_to_guid_folders
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from app.core.settings import ROOT_DIR, USER_DATA_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate() -> None:
  for base_dir in [ROOT_DIR / "local", USER_DATA_DIR]:
    old_transcriptions_dir = base_dir / "transcriptions"
    old_media_dir = base_dir / "media" / "uploads"
    manifest_path = base_dir / "media" / "manifest.json"

    if not old_transcriptions_dir.exists():
      continue

    manifest_map = {}
    if manifest_path.exists():
      try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(manifest_data, list):
          manifest_map = {m["id"]: m for m in manifest_data if isinstance(m, dict) and "id" in m}
      except Exception:
        pass

    target_transcriptions_dir = USER_DATA_DIR / "transcriptions"
    target_transcriptions_dir.mkdir(parents=True, exist_ok=True)

    for json_file in list(old_transcriptions_dir.glob("*.json")):
      if json_file.name == "manifest.json" or json_file.parent.name == "active_jobs":
        continue
      try:
        record = json.loads(json_file.read_text(encoding="utf-8"))
      except Exception:
        continue

      tid = record.get("id")
      if not tid:
        continue

      new_folder = target_transcriptions_dir / tid
      new_folder.mkdir(parents=True, exist_ok=True)

      media_id = record.get("media_id")
      media_entry = manifest_map.get(media_id, {})
      old_media_path = Path(media_entry.get("path", "")) if media_entry else None

      if not old_media_path or not old_media_path.exists():
        stored_name = media_entry.get("stored_filename", "")
        if stored_name and (old_media_dir / stored_name).exists():
          old_media_path = old_media_dir / stored_name

      if old_media_path and old_media_path.exists():
        ext = old_media_path.suffix.lower()
        shutil.copy2(old_media_path, new_folder / f"media{ext}")
        record["media"] = {
          "original_filename": media_entry.get("filename", old_media_path.name),
          "stored_filename": f"media{ext}",
          "size_bytes": media_entry.get("size_bytes", old_media_path.stat().st_size),
          "is_video": media_entry.get("is_video", False),
          "hash": media_entry.get("hash", ""),
        }

      record.pop("media_id", None)

      (new_folder / "transcription.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
      )

      if record.get("text"):
        (new_folder / "transcript.txt").write_text(record["text"], encoding="utf-8")

      if json_file != (new_folder / "transcription.json") and json_file.is_file():
        try:
          json_file.unlink()
        except Exception:
          pass

      logger.info(f"Migrated transcription to GUID layout: {tid}")

  logger.info("GUID layout migration complete.")


if __name__ == "__main__":
  migrate()

"""Re-encrypt legacy Fernet values with AES-256-GCM (SEC-01).

Legacy formats found in the database:
- "enc::<fernet token>": API keys and tokens; key = PBKDF2-HMAC-SHA256(SECRET_KEY, PBKDF2_SALT).
- "gAAAA...": organization integration payloads; key = SHA-256(SECRET_KEY).

The script scans every text/JSON column of every table, including JSON documents stored as
text, and replaces each legacy value with its "gcm::" equivalent. Run it once, with the same
SECRET_KEY and PBKDF2_SALT, before starting the new version.

Usage (from backend/):
    python -m scripts.migrate_fernet_to_gcm           # dry run: count only
    python -m scripts.migrate_fernet_to_gcm --apply   # re-encrypt
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import JSON, MetaData, String, Table, Text, inspect, select, update
from sqlalchemy.dialects.postgresql import JSONB

from app.core.secrets import PBKDF2_ITERATIONS, _get_master_secret, _get_pbkdf2_salt, encrypt_bytes
from app.db.database import get_sync_engine

LEGACY_PREFIX = "enc::"
FERNET_TOKEN_PREFIX = "gAAAAA"


def _legacy_ciphers() -> tuple[Fernet, Fernet]:
  master = _get_master_secret()
  pbkdf2_key = hashlib.pbkdf2_hmac("sha256", master.encode("utf-8"), _get_pbkdf2_salt(), PBKDF2_ITERATIONS, dklen=32)
  sha_key = hashlib.sha256(master.encode("utf-8")).digest()
  return Fernet(base64.urlsafe_b64encode(pbkdf2_key)), Fernet(base64.urlsafe_b64encode(sha_key))


PREFIXED, RAW = _legacy_ciphers()


def _convert_str(value: str) -> str | None:
  """Return the re-encrypted value, or None when the string is not a legacy token."""
  if value.startswith(LEGACY_PREFIX):
    plain = PREFIXED.decrypt(value[len(LEGACY_PREFIX):].encode("ascii"))
    return encrypt_bytes(plain)
  if value.startswith(FERNET_TOKEN_PREFIX):
    try:
      plain = RAW.decrypt(value.encode("ascii"))
    except InvalidToken:
      return None
    return encrypt_bytes(plain)
  return None


def _convert(value: Any) -> tuple[Any, int]:
  """Walk strings, dicts, lists and JSON-in-text; return (new value, converted count)."""
  if isinstance(value, dict):
    total = 0
    out = {}
    for k, v in value.items():
      out[k], n = _convert(v)
      total += n
    return out, total
  if isinstance(value, list):
    total = 0
    out_list = []
    for v in value:
      nv, n = _convert(v)
      out_list.append(nv)
      total += n
    return out_list, total
  if isinstance(value, str):
    converted = _convert_str(value)
    if converted is not None:
      return converted, 1
    stripped = value.lstrip()
    if stripped[:1] in ("{", "[", '"') and (LEGACY_PREFIX in value or FERNET_TOKEN_PREFIX in value):
      try:
        parsed = json.loads(value)
      except ValueError:
        return value, 0
      new, n = _convert(parsed)
      if n:
        return json.dumps(new, ensure_ascii=False), n
  return value, 0


def main(apply: bool) -> int:
  engine = get_sync_engine()
  inspector = inspect(engine)
  grand_total = 0
  with engine.begin() as conn:
    for table_name in inspector.get_table_names():
      columns = inspector.get_columns(table_name)
      pk = inspector.get_pk_constraint(table_name).get("constrained_columns") or []
      targets = [c["name"] for c in columns if isinstance(c["type"], (String, Text, JSON, JSONB))]
      if not targets or not pk:
        continue
      table = Table(table_name, MetaData(), autoload_with=conn)
      for row in conn.execute(select(table)).mappings():
        changes: dict[str, Any] = {}
        for col in targets:
          if row[col] is None:
            continue
          new, n = _convert(row[col])
          if n:
            changes[col] = new
            grand_total += n
        if changes:
          print(f"{table_name}: {', '.join(changes)} ({ {k: row[k] for k in pk} })")
          if apply:
            cond = [table.c[k] == row[k] for k in pk]
            conn.execute(update(table).where(*cond).values(**changes))
    if not apply:
      conn.rollback()
  print(f"{grand_total} valor(es) Fernet {'re-cifrados con AES-256-GCM' if apply else 'por migrar (ejecución en seco; usa --apply)'}.")
  return 0


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--apply", action="store_true", help="Escribe los valores re-cifrados.")
  sys.exit(main(parser.parse_args().apply))

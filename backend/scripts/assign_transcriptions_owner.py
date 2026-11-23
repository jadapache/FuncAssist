"""Assign ownerless transcriptions (created before per-user isolation) to a user.

Usage (from backend/):
    python -m scripts.assign_transcriptions_owner --user <user id>          # dry run: count only
    python -m scripts.assign_transcriptions_owner --user <user id> --apply  # assign
    python -m scripts.assign_transcriptions_owner --user <user id> --apply --all  # reassign every record
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.transcription_migration import migrate_transcriptions_if_needed
from app.db.database import get_db, init_db
from app.db.repositories.transcription_repository import TranscriptionRepository


async def _main(user_id: str, apply: bool, all_records: bool) -> int:
  await init_db()
  migrate_transcriptions_if_needed()
  async with get_db() as db:
    repo = TranscriptionRepository(db)
    records = await repo.list()
    targets = [r for r in records if all_records or not r.get("user_id")]
    print(f"{len(targets)} transcripción(es) {'en total' if all_records else 'sin propietario'}.")
    if not apply:
      print("Ejecución en seco: usa --apply para asignarlas.")
      return 0
    count = await repo.assign_owner(user_id, only_unowned=not all_records)
    print(f"Asignadas {count} transcripción(es) al usuario {user_id}.")
  return 0


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--user", required=True, help="Id del usuario propietario")
  parser.add_argument("--apply", action="store_true", help="Escribe los cambios (por defecto solo cuenta)")
  parser.add_argument("--all", action="store_true", help="Reasigna también las que ya tienen propietario")
  args = parser.parse_args()
  sys.exit(asyncio.run(_main(args.user, args.apply, args.all)))


if __name__ == "__main__":
  main()

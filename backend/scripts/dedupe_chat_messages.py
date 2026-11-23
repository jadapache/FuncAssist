"""Remove historical duplicate chat messages.

Before client-generated message ids, the agentic endpoint and the client autosave could both store
the same turn. A duplicate is a message with the same session, role and content as the message right
before it in that session, created less than WINDOW seconds later. The first copy is kept.

Dry run by default (prints what would be deleted):
    python -m scripts.dedupe_chat_messages
    python -m scripts.dedupe_chat_messages --session cbff759a-...    # one conversation
Delete:
    python -m scripts.dedupe_chat_messages --apply
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
  sys.path.insert(0, str(backend_root))

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SECONDS = 10.0


def _as_utc(value: datetime | None) -> datetime | None:
  if value is None:
    return None
  return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def find_duplicate_ids(messages: Sequence[object], window_seconds: float = DEFAULT_WINDOW_SECONDS) -> list[str]:
  """Ids of duplicates in `messages` (one session, ordered by created_at, then id).

  A message is a duplicate when the previous message of the session has the same role and the same
  content (ignoring surrounding whitespace) and was created less than `window_seconds` earlier.
  Comparison is always against the previous message, so in a run of copies all but the first go.
  """
  duplicates: list[str] = []
  previous = None
  for msg in messages:
    if previous is not None:
      same_turn = (
        getattr(msg, "role", None) == getattr(previous, "role", None)
        and (getattr(msg, "content", "") or "").strip() == (getattr(previous, "content", "") or "").strip()
      )
      t_prev = _as_utc(getattr(previous, "created_at", None))
      t_cur = _as_utc(getattr(msg, "created_at", None))
      close = t_prev is not None and t_cur is not None and 0 <= (t_cur - t_prev).total_seconds() < window_seconds
      if same_turn and close:
        duplicates.append(getattr(msg, "id"))
        continue  # keep comparing against the first copy
    previous = msg
  return duplicates


def _group_by_session(rows: Iterable[object]) -> dict[str, list[object]]:
  sessions: dict[str, list[object]] = {}
  for row in rows:
    sessions.setdefault(getattr(row, "session_id"), []).append(row)
  return sessions


def run(apply: bool, session_prefix: str | None, window_seconds: float) -> int:
  from sqlalchemy import delete, select

  from app.db.database import get_sync_db
  from app.db.models import ChatMessageModel

  with get_sync_db() as db:
    stmt = select(ChatMessageModel).order_by(
      ChatMessageModel.session_id, ChatMessageModel.created_at, ChatMessageModel.id
    )
    if session_prefix:
      stmt = stmt.where(ChatMessageModel.session_id.like(f"{session_prefix}%"))
    rows = db.execute(stmt).scalars().all()

    to_delete: list[str] = []
    for session_id, messages in _group_by_session(rows).items():
      ids = find_duplicate_ids(messages, window_seconds)
      if not ids:
        continue
      by_id = {m.id: m for m in messages}
      logger.info("Session %s: %d duplicate(s)", session_id, len(ids))
      for msg_id in ids:
        msg = by_id[msg_id]
        preview = (msg.content or "").strip().replace("\n", " ")[:80]
        logger.info("  - %s [%s] %s  %r", msg_id, msg.role, msg.created_at, preview)
      to_delete.extend(ids)

    logger.info("%d message(s) checked, %d duplicate(s) found.", len(rows), len(to_delete))
    if not to_delete:
      return 0
    if not apply:
      logger.info("Dry run: nothing deleted. Re-run with --apply to delete them.")
      return len(to_delete)

    for start in range(0, len(to_delete), 500):
      batch = to_delete[start:start + 500]
      db.execute(delete(ChatMessageModel).where(ChatMessageModel.id.in_(batch)))
    db.commit()
    logger.info("Deleted %d duplicate message(s).", len(to_delete))
    return len(to_delete)


def main(argv: Sequence[str] | None = None) -> None:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--apply", action="store_true", help="Delete the duplicates (default: dry run).")
  parser.add_argument("--session", help="Only sessions whose id starts with this prefix.")
  parser.add_argument(
    "--window", type=float, default=DEFAULT_WINDOW_SECONDS,
    help=f"Max seconds between copies (default {DEFAULT_WINDOW_SECONDS:g}).",
  )
  args = parser.parse_args(argv)
  logging.basicConfig(level=logging.INFO, format="%(message)s")
  run(apply=args.apply, session_prefix=args.session, window_seconds=args.window)


if __name__ == "__main__":
  main()

"""Checks on the credential an administrator connects as a service account.

A service account is a bot identity dedicated to the integration. It must be able to read what the
application needs and nothing more: a credential with write or administration access is rejected when it
is connected and again whenever the connection is tested, so a token whose permissions grew later stops
being accepted.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

EXPIRY_WARNING_DAYS = 14

# GitLab token scopes: what is acceptable, and what the integration cannot work without.
GITLAB_ALLOWED_SCOPES = frozenset({"read_api", "read_repository", "read_user"})
GITLAB_REQUIRED_SCOPES = frozenset({"read_api"})


def check_scopes(granted: Iterable[str], *, allowed: Iterable[str], required: Iterable[str] = ()) -> list[str]:
  """The granted scopes, sorted, when they are acceptable. Raises ValueError otherwise."""
  granted_set = {str(s).strip() for s in granted if str(s).strip()}
  allowed_set, required_set = set(allowed), set(required)
  excess = sorted(granted_set - allowed_set)
  if excess:
    raise ValueError(
      "The credential has more access than a read-only service account needs: "
      f"{', '.join(excess)}. Create it with only: {', '.join(sorted(allowed_set))}."
    )
  missing = sorted(required_set - granted_set)
  if missing:
    raise ValueError(f"The credential lacks a required permission: {', '.join(missing)}.")
  return sorted(granted_set)


def parse_expiry(value: Any) -> Optional[datetime]:
  """A timezone-aware datetime from an ISO date or datetime, or None when there is no expiry."""
  if not value:
    return None
  text = str(value).strip()
  try:
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
  except ValueError:
    return None
  if parsed.tzinfo is None:
    parsed = parsed.replace(tzinfo=timezone.utc)
  if len(text) <= 10:  # a bare date expires at the end of that day
    parsed = parsed + timedelta(days=1) - timedelta(seconds=1)
  return parsed


def days_until_expiry(expires_at: Any, now: Optional[datetime] = None) -> Optional[int]:
  expiry = parse_expiry(expires_at)
  if expiry is None:
    return None
  return (expiry - (now or datetime.now(timezone.utc))).days


def expiry_state(expires_at: Any, now: Optional[datetime] = None) -> str:
  """none (never expires), ok, expiring (within the warning window) or expired."""
  expiry = parse_expiry(expires_at)
  if expiry is None:
    return "none"
  current = now or datetime.now(timezone.utc)
  if expiry <= current:
    return "expired"
  return "expiring" if expiry - current <= timedelta(days=EXPIRY_WARNING_DAYS) else "ok"

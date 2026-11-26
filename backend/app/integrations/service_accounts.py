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


# GitHub App permissions: read-only access to exactly what the integration queries.
GITHUB_ALLOWED_PERMISSIONS = frozenset({"metadata", "contents", "pull_requests", "issues"})
GITHUB_REQUIRED_PERMISSIONS = frozenset({"metadata", "contents", "pull_requests"})


def check_app_permissions(
  granted: dict[str, Any],
  *,
  allowed: Iterable[str] = GITHUB_ALLOWED_PERMISSIONS,
  required: Iterable[str] = GITHUB_REQUIRED_PERMISSIONS,
) -> dict[str, str]:
  """The granted permissions of a GitHub App installation when they are read-only and no more than needed.

  Raises ValueError on any write or admin level, on any permission outside the allowed set, or when a
  required permission is missing.
  """
  perms = {str(k): str(v) for k, v in (granted or {}).items()}
  writable = sorted(name for name, level in perms.items() if level != "read")
  if writable:
    raise ValueError(
      "The GitHub App has write or admin access, which a read-only integration must not have: "
      f"{', '.join(writable)}. Set these permissions to 'Read-only' or 'No access'."
    )
  excess = sorted(set(perms) - set(allowed))
  if excess:
    raise ValueError(
      "The GitHub App has more access than needed: "
      f"{', '.join(excess)}. Allowed: {', '.join(sorted(allowed))}."
    )
  missing = sorted(set(required) - set(perms))
  if missing:
    raise ValueError(f"The GitHub App lacks a required permission: {', '.join(missing)} (read-only).")
  return dict(sorted(perms.items()))


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

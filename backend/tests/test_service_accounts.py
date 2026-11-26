"""Service account credentials: scope checks and expiry states."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.integrations import service_accounts as sa

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
ALLOWED = sa.GITLAB_ALLOWED_SCOPES
REQUIRED = sa.GITLAB_REQUIRED_SCOPES


def test_read_only_scopes_are_accepted_and_returned_sorted():
  assert sa.check_scopes(["read_repository", "read_api"], allowed=ALLOWED, required=REQUIRED) == ["read_api", "read_repository"]
  assert sa.check_scopes(["read_api"], allowed=ALLOWED, required=REQUIRED) == ["read_api"]
  assert sa.check_scopes([" read_api ", "", "read_api"], allowed=ALLOWED, required=REQUIRED) == ["read_api"]


@pytest.mark.parametrize("scopes", [
  ["api"],
  ["read_api", "write_repository"],
  ["read_api", "sudo"],
  ["read_api", "admin_mode"],
  ["read_api", "create_runner", "manage_runner"],
  ["read_api", "self_rotate"],
])
def test_scopes_beyond_read_only_are_rejected_and_named(scopes):
  with pytest.raises(ValueError, match="more access") as exc:
    sa.check_scopes(scopes, allowed=ALLOWED, required=REQUIRED)
  assert any(s in str(exc.value) for s in scopes if s not in ALLOWED)


def test_a_missing_required_scope_is_rejected():
  with pytest.raises(ValueError, match="lacks a required permission: read_api"):
    sa.check_scopes(["read_repository"], allowed=ALLOWED, required=REQUIRED)
  with pytest.raises(ValueError, match="lacks"):
    sa.check_scopes([], allowed=ALLOWED, required=REQUIRED)


def test_required_scopes_are_optional():
  assert sa.check_scopes(["read_user"], allowed=ALLOWED) == ["read_user"]


@pytest.mark.parametrize("value,expected", [
  (None, None), ("", None), ("not a date", None),
  ("2026-12-01T10:00:00Z", datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc)),
  ("2026-12-01T10:00:00+02:00", datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)),
  ("2026-12-01T10:00:00", datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc)),
  ("2026-12-01", datetime(2026, 12, 1, 23, 59, 59, tzinfo=timezone.utc)),
])
def test_parse_expiry(value, expected):
  assert sa.parse_expiry(value) == expected


@pytest.mark.parametrize("expires,state,days", [
  (None, "none", None),
  ("2027-01-01", "ok", 37),
  ((NOW + timedelta(days=10)).isoformat(), "expiring", 10),
  ((NOW + timedelta(days=sa.EXPIRY_WARNING_DAYS)).isoformat(), "expiring", sa.EXPIRY_WARNING_DAYS),
  ((NOW + timedelta(days=sa.EXPIRY_WARNING_DAYS, seconds=1)).isoformat(), "ok", sa.EXPIRY_WARNING_DAYS),
  ((NOW - timedelta(days=1)).isoformat(), "expired", -1),
  (NOW.isoformat(), "expired", 0),
])
def test_expiry_state_and_days(expires, state, days):
  assert sa.expiry_state(expires, NOW) == state
  assert sa.days_until_expiry(expires, NOW) == days


def test_expiry_defaults_to_the_current_time():
  assert sa.expiry_state((datetime.now(timezone.utc) + timedelta(days=400)).isoformat()) == "ok"
  assert sa.expiry_state("2000-01-01") == "expired"

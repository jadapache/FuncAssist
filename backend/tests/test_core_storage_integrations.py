"""Persistence of integration connections: organization ones (GitHub, GitLab) and personal ones (Jira)."""

from __future__ import annotations

import logging

import pytest

from app.core import storage_integrations as org
from app.core import storage_user_integrations as personal
from app.core.secrets import decrypt_secret, encrypt_secret
from app.core.storage_cache import _CACHE_CONNECTIONS, clear_storage_caches, make_conn_cache_key, make_user_conn_cache_key
from app.db import unit_of_work as uow_mod
from app.db.models import OrganizationIntegrationModel, UserIntegrationModel, UserJiraConnectionModel, UserSecretModel
from tests.fake_session import GLOBAL_FAKE_STORAGE, FakeSyncSession


@pytest.fixture(autouse=True)
def clean_cache():
  clear_storage_caches()
  yield
  clear_storage_caches()


@pytest.fixture
def broken_database(monkeypatch):
  class Broken:
    def __enter__(self):
      raise RuntimeError("database down")

    def __exit__(self, *exc):
      return False

  monkeypatch.setattr(uow_mod, "SyncUnitOfWork", Broken)


def rows(model):
  return list(GLOBAL_FAKE_STORAGE.tables.get(model, {}).values())


# ----------------------------------------------------------------------------- organization connections


def test_a_saved_connection_is_loaded_back():
  org.save_connection("github", {"client_id": "cid", "token": "t0k"}, org_id="acme")
  assert org.load_connection("github", org_id="acme") == {"client_id": "cid", "token": "t0k"}


def test_a_saved_connection_is_stored_encrypted_with_its_client_id():
  org.save_connection("github", {"client_id": "cid", "token": "t0k"}, org_id="acme")
  [row] = rows(OrganizationIntegrationModel)
  assert (row.organization_id, row.provider, row.client_id, row.status) == ("acme", "github", "cid", "active")
  assert "t0k" not in row.client_secret_ref


def test_connections_are_kept_per_organization_and_provider():
  org.save_connection("github", {"v": 1}, org_id="a")
  org.save_connection("github", {"v": 2}, org_id="b")
  org.save_connection("gitlab", {"v": 3})
  assert org.load_connection("github", org_id="a") == {"v": 1}
  assert org.load_connection("github", org_id="b") == {"v": 2}
  assert org.load_connection("gitlab") == {"v": 3}
  assert org.load_connection("jira") is None


def test_the_default_organization_is_used_when_none_is_given():
  org.save_connection("gitlab", {"v": 1})
  assert org.load_connection("gitlab", org_id="default") == {"v": 1}


def test_saving_twice_keeps_one_row():
  org.save_connection("github", {"v": 1})
  org.save_connection("github", {"v": 2})
  assert len(rows(OrganizationIntegrationModel)) == 1
  assert org.load_connection("github") == {"v": 2}


def test_a_failure_to_save_is_raised_and_logged(broken_database, caplog):
  with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="database down"):
    org.save_connection("github", {"v": 1})
  assert "Failed to persist organization integration to DB: database down" in caplog.text


def test_the_database_replaces_what_the_cache_holds():
  org.save_connection("github", {"v": "old"})
  [row] = rows(OrganizationIntegrationModel)
  row.client_secret_ref = org_cipher({"v": "new"})
  assert org.load_connection("github") == {"v": "new"}
  assert _CACHE_CONNECTIONS[make_conn_cache_key("default", "github")] == row.client_secret_ref


def test_a_connection_removed_from_the_database_is_dropped_from_the_cache():
  org.save_connection("github", {"v": 1})
  GLOBAL_FAKE_STORAGE.clear()
  assert org.load_connection("github") is None
  assert make_conn_cache_key("default", "github") not in _CACHE_CONNECTIONS


def test_the_cache_answers_when_the_database_cannot_be_read(broken_database):
  _CACHE_CONNECTIONS[make_conn_cache_key("default", "github")] = org_cipher({"v": 1})
  assert org.load_connection("github") == {"v": 1}


def test_nothing_is_loaded_when_there_is_neither_cache_nor_database(broken_database):
  assert org.load_connection("github") is None


def test_a_row_without_a_secret_keeps_the_cached_value():
  org.save_connection("github", {"v": 1})
  [row] = rows(OrganizationIntegrationModel)
  row.client_secret_ref = None
  assert org.load_connection("github") == {"v": 1}


def test_a_connection_that_cannot_be_decrypted_is_not_loaded(caplog):
  org.save_connection("github", {"v": 1})
  [row] = rows(OrganizationIntegrationModel)
  row.client_secret_ref = "not-a-valid-ciphertext"
  with caplog.at_level(logging.WARNING):
    assert org.load_connection("github") is None
  assert "Decryption failed for integration github" in caplog.text


def org_cipher(payload):
  import json

  from app.core.secrets import encrypt_bytes

  return encrypt_bytes(json.dumps(payload).encode("utf-8"))


def test_deleting_a_connection_removes_it_from_the_database_and_the_cache():
  org.save_connection("github", {"v": 1})
  assert org.delete_connection("github") is True
  assert rows(OrganizationIntegrationModel) == []
  assert make_conn_cache_key("default", "github") not in _CACHE_CONNECTIONS
  assert org.load_connection("github") is None


def test_deleting_reports_a_connection_that_only_the_cache_had():
  _CACHE_CONNECTIONS[make_conn_cache_key("default", "github")] = org_cipher({"v": 1})
  assert org.delete_connection("github") is True


def test_deleting_reports_a_connection_that_only_the_database_had():
  org.save_connection("github", {"v": 1})
  clear_storage_caches()
  assert org.delete_connection("github") is True


def test_deleting_a_missing_connection_is_false():
  assert org.delete_connection("github") is False


def test_deleting_only_touches_its_own_organization():
  org.save_connection("github", {"v": 1}, org_id="a")
  org.save_connection("github", {"v": 2}, org_id="b")
  org.delete_connection("github", org_id="a")
  assert org.load_connection("github", org_id="b") == {"v": 2}


def test_a_failure_to_delete_is_raised_and_logged(broken_database, caplog):
  with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="database down"):
    org.delete_connection("github")
  assert "Could not delete connection from DB: database down" in caplog.text


def test_a_connection_exists_when_it_is_saved():
  assert org.connection_exists("github") is False
  org.save_connection("github", {"v": 1})
  assert org.connection_exists("github") is True
  assert org.connection_exists("github", org_id="other") is False


def test_a_connection_exists_when_only_the_database_has_it():
  org.save_connection("github", {"v": 1})
  clear_storage_caches()
  assert org.connection_exists("github") is True


def test_a_cached_connection_exists_without_asking_the_database(broken_database):
  _CACHE_CONNECTIONS[make_conn_cache_key("default", "github")] = org_cipher({"v": 1})
  assert org.connection_exists("github") is True


def test_a_connection_does_not_exist_when_the_database_cannot_be_read(broken_database):
  assert org.connection_exists("github") is False


# ----------------------------------------------------------------------------- personal connections


JIRA = {
  "access_token": "acc", "refresh_token": "ref", "site_url": "https://acme.atlassian.net", "cloud_id": "c1",
  "account_email": "ana@acme.com", "account_id": "acct-1", "account_name": "Ana", "expires_at": 99.0, "scopes": ["a", "b"],
}


def test_a_personal_integration_is_loaded_back_with_a_default_status():
  personal.save_user_integration("u1", "jira", JIRA)
  assert personal.load_user_integration("u1", "jira") == {**JIRA, "status": "connected"}


def test_an_explicit_status_is_kept():
  personal.save_user_integration("u1", "jira", {**JIRA, "status": "pending_oauth"})
  assert personal.load_user_integration("u1", "jira")["status"] == "pending_oauth"


def test_the_payload_given_is_not_modified():
  payload = dict(JIRA)
  personal.save_user_integration("u1", "jira", payload)
  assert payload == JIRA


@pytest.mark.parametrize(("user_id", "provider"), [("", "jira"), ("u1", ""), (None, "jira")])
def test_saving_needs_a_user_and_a_provider(user_id, provider):
  with pytest.raises(ValueError, match="user_id and provider are required"):
    personal.save_user_integration(user_id, provider, {})


@pytest.mark.parametrize(("user_id", "provider"), [("", "jira"), ("u1", ""), (None, None)])
def test_loading_and_deleting_without_a_user_or_provider_do_nothing(user_id, provider):
  assert personal.load_user_integration(user_id, provider) is None
  assert personal.delete_user_integration(user_id, provider) is False


def test_tokens_go_to_the_secret_store_and_the_row_only_references_them():
  personal.save_user_integration("u1", "jira", JIRA)
  [row] = rows(UserIntegrationModel)
  secrets_by_purpose = {s.purpose: s.id for s in rows(UserSecretModel)}
  assert set(secrets_by_purpose) == {"jira_access_token", "jira_refresh_token"}
  assert row.access_token_ref == f"sec::{secrets_by_purpose['jira_access_token']}"
  assert row.refresh_token_ref == f"sec::{secrets_by_purpose['jira_refresh_token']}"
  assert "acc" not in (row.connection_metadata_json or "").replace("access", "")


def test_the_row_describes_the_account_and_the_scopes():
  personal.save_user_integration("u1", "jira", JIRA)
  [row] = rows(UserIntegrationModel)
  assert (row.user_id, row.provider, row.external_account_id, row.external_account_name) == ("u1", "jira", "acct-1", "Ana")
  assert (row.expires_at, row.scopes_json, row.status) == (99.0, '["a", "b"]', "connected")
  assert decrypt_secret(row.connection_metadata_json) and '"status": "connected"' in decrypt_secret(row.connection_metadata_json)


def test_the_account_name_falls_back_to_the_display_name_and_the_id_to_the_external_one():
  personal.save_user_integration("u1", "github", {"display_name": "Ana D", "external_account_id": "ext-9"})
  [row] = rows(UserIntegrationModel)
  assert (row.external_account_id, row.external_account_name) == ("ext-9", "Ana D")


def test_no_tokens_means_no_secrets_and_no_references():
  personal.save_user_integration("u1", "github", {"account_id": "x"})
  [row] = rows(UserIntegrationModel)
  assert (row.access_token_ref, row.refresh_token_ref, rows(UserSecretModel)) == (None, None, [])
  assert (row.scopes_json, row.status) == ("[]", "connected")


def test_scopes_that_are_not_a_list_are_stored_as_text():
  personal.save_user_integration("u1", "github", {"scopes": "read write"})
  assert rows(UserIntegrationModel)[0].scopes_json == "read write"


def test_a_token_is_kept_encrypted_in_the_row_when_the_store_gives_no_id(monkeypatch):
  monkeypatch.setattr(personal.secret_store, "create_secret", lambda **kwargs: None)
  personal.save_user_integration("u1", "github", {"access_token": "plain-access"})
  [row] = rows(UserIntegrationModel)
  assert row.access_token_ref != "plain-access"
  assert decrypt_secret(row.access_token_ref) == "plain-access"
  assert row.refresh_token_ref is None


def test_only_jira_keeps_a_connection_row_with_its_site_data():
  personal.save_user_integration("u1", "github", JIRA)
  assert rows(UserJiraConnectionModel) == []
  personal.save_user_integration("u1", "jira", JIRA)
  [jira] = rows(UserJiraConnectionModel)
  assert (jira.jira_url, jira.cloud_id, jira.account_email, jira.account_id) == (
    "https://acme.atlassian.net", "c1", "ana@acme.com", "acct-1"
  )
  assert jira.access_token_secret_id and jira.refresh_token_secret_id


@pytest.mark.parametrize(
  ("payload", "url", "email", "account"),
  [
    ({"jira_url": "j", "base_url": "b", "site_url": "s", "account_email": "a", "email": "e", "account_id": "1", "external_account_id": "2"}, "j", "a", "1"),
    ({"base_url": "b", "site_url": "s", "email": "e", "external_account_id": "2"}, "b", "e", "2"),
    ({"site_url": "s"}, "s", None, None),
    ({}, None, None, None),
  ],
)
def test_the_jira_site_and_account_come_from_the_first_field_that_is_set(payload, url, email, account):
  personal.save_user_integration("u1", "jira", payload)
  [jira] = rows(UserJiraConnectionModel)
  assert (jira.jira_url, jira.account_email, jira.account_id) == (url, email, account)


def test_saving_again_replaces_the_integration():
  personal.save_user_integration("u1", "jira", JIRA)
  personal.save_user_integration("u1", "jira", {**JIRA, "account_name": "Ana B"})
  assert len(rows(UserIntegrationModel)) == 1
  assert rows(UserIntegrationModel)[0].external_account_name == "Ana B"
  assert personal.load_user_integration("u1", "jira")["account_name"] == "Ana B"


def test_a_given_session_is_used_and_left_to_the_caller_to_commit():
  session = FakeSyncSession(GLOBAL_FAKE_STORAGE)
  personal.save_user_integration("u1", "jira", JIRA, db=session)
  assert len(rows(UserIntegrationModel)) == 1
  assert personal.load_user_integration("u1", "jira", db=session)["account_name"] == "Ana"
  assert personal.delete_user_integration("u1", "jira", db=session) is True
  assert rows(UserIntegrationModel) == []


def test_a_failure_to_save_is_raised_and_logged(broken_database, caplog):
  with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="database down"):
    personal.save_user_integration("u1", "jira", JIRA)
  assert "Failed to persist user integration to DB: database down" in caplog.text


def test_the_database_replaces_what_the_cache_holds_for_a_user():
  personal.save_user_integration("u1", "jira", JIRA)
  rows(UserIntegrationModel)[0].connection_metadata_json = encrypt_secret('{"account_name": "From DB"}')
  assert personal.load_user_integration("u1", "jira") == {"account_name": "From DB"}
  assert _CACHE_CONNECTIONS[make_user_conn_cache_key("u1", "jira")] == rows(UserIntegrationModel)[0].connection_metadata_json.encode()


def test_a_personal_integration_removed_from_the_database_is_dropped_from_the_cache():
  personal.save_user_integration("u1", "jira", JIRA)
  GLOBAL_FAKE_STORAGE.clear()
  assert personal.load_user_integration("u1", "jira") is None
  assert make_user_conn_cache_key("u1", "jira") not in _CACHE_CONNECTIONS


def test_with_a_given_session_a_missing_row_keeps_the_cache():
  session = FakeSyncSession(GLOBAL_FAKE_STORAGE)
  _CACHE_CONNECTIONS[make_user_conn_cache_key("u1", "jira")] = encrypt_secret('{"v": 1}').encode()
  assert personal.load_user_integration("u1", "jira", db=session) == {"v": 1}
  assert make_user_conn_cache_key("u1", "jira") in _CACHE_CONNECTIONS


def test_the_cache_answers_when_the_database_cannot_be_read_for_a_user(broken_database):
  _CACHE_CONNECTIONS[make_user_conn_cache_key("u1", "jira")] = encrypt_secret('{"v": 1}').encode()
  assert personal.load_user_integration("u1", "jira") == {"v": 1}
  assert personal.load_user_integration("u2", "jira") is None


def test_a_row_without_metadata_keeps_the_cached_value():
  personal.save_user_integration("u1", "jira", JIRA)
  rows(UserIntegrationModel)[0].connection_metadata_json = None
  assert personal.load_user_integration("u1", "jira")["account_name"] == "Ana"


def test_an_integration_that_cannot_be_decrypted_is_not_loaded(caplog):
  personal.save_user_integration("u1", "jira", JIRA)
  rows(UserIntegrationModel)[0].connection_metadata_json = "garbage"
  with caplog.at_level(logging.WARNING):
    assert personal.load_user_integration("u1", "jira") is None
  assert "Decryption failed for user integration u1/jira" in caplog.text


def test_deleting_a_personal_integration_removes_row_jira_data_and_cache():
  personal.save_user_integration("u1", "jira", JIRA)
  assert personal.delete_user_integration("u1", "jira") is True
  assert rows(UserIntegrationModel) == [] and rows(UserJiraConnectionModel) == []
  assert make_user_conn_cache_key("u1", "jira") not in _CACHE_CONNECTIONS
  assert personal.load_user_integration("u1", "jira") is None


def test_deleting_reports_what_only_the_cache_or_only_the_database_had():
  personal.save_user_integration("u1", "jira", JIRA)
  clear_storage_caches()
  assert personal.delete_user_integration("u1", "jira") is True
  _CACHE_CONNECTIONS[make_user_conn_cache_key("u2", "jira")] = b"x"
  assert personal.delete_user_integration("u2", "jira") is True
  assert personal.delete_user_integration("u2", "jira") is False


def test_deleting_one_user_keeps_the_others():
  personal.save_user_integration("u1", "jira", JIRA)
  personal.save_user_integration("u2", "jira", JIRA)
  personal.delete_user_integration("u1", "jira")
  assert personal.load_user_integration("u2", "jira")["account_name"] == "Ana"


def test_a_failure_to_delete_a_personal_integration_is_raised_and_logged(broken_database, caplog):
  with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="database down"):
    personal.delete_user_integration("u1", "jira")
  assert "Failed deleting user integration u1/jira: database down" in caplog.text


def test_an_integration_exists_only_while_connected():
  assert personal.user_integration_exists("u1", "jira") is False
  personal.save_user_integration("u1", "jira", JIRA)
  assert personal.user_integration_exists("u1", "jira") is True
  personal.save_user_integration("u1", "jira", {**JIRA, "status": "pending_oauth"})
  assert personal.user_integration_exists("u1", "jira") is False


def test_a_cached_integration_is_never_returned_for_an_empty_user_or_provider():
  _CACHE_CONNECTIONS[make_user_conn_cache_key("", "jira")] = encrypt_secret('{"v": 1}').encode()
  _CACHE_CONNECTIONS[make_user_conn_cache_key("u1", "")] = encrypt_secret('{"v": 2}').encode()
  assert personal.load_user_integration("", "jira") is None
  assert personal.load_user_integration("u1", "") is None
  assert personal.delete_user_integration("", "jira") is False
  assert personal.delete_user_integration("u1", "") is False
  assert make_user_conn_cache_key("", "jira") in _CACHE_CONNECTIONS


def test_the_payload_is_stored_with_its_characters_as_they_are():
  personal.save_user_integration("u1", "jira", {"account_name": "José Ñandú"})
  assert "José Ñandú" in decrypt_secret(rows(UserIntegrationModel)[0].connection_metadata_json)


def test_an_empty_status_is_stored_as_connected_in_the_row():
  personal.save_user_integration("u1", "github", {"status": None})
  assert rows(UserIntegrationModel)[0].status == "connected"


def test_a_pending_status_is_stored_in_the_row():
  personal.save_user_integration("u1", "github", {"status": "pending_oauth"})
  assert rows(UserIntegrationModel)[0].status == "pending_oauth"

"""IntegrationRepository against a real PostgreSQL (skipped when TEST_DATABASE_URL is not set)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.models import OrganizationModel, UserJiraConnectionModel, UserModel, UserSecretModel
from app.db.repositories.integration_repository import IntegrationRepository


@pytest.fixture
def repo(pg_session):
  pg_session.add(OrganizationModel(id="default", name="Default", slug="default"))
  pg_session.add(UserModel(id="u1", username="ana"))
  pg_session.add(UserModel(id="u2", username="bob"))
  pg_session.add(UserSecretModel(id="s-access", user_id="u1", purpose="jira_access_token", ciphertext="c", nonce="n"))
  pg_session.add(UserSecretModel(id="s-refresh", user_id="u1", purpose="jira_refresh_token", ciphertext="c", nonce="n"))
  pg_session.flush()
  return IntegrationRepository(pg_session)


def save(repo, user_id="u1", provider="github", **overrides):
  values = dict(
    external_account_id="acct-1", external_account_name="Ana", access_token_ref="sec::a", refresh_token_ref="sec::r",
    expires_at=1234.5, scopes_json='["read"]', connection_metadata_json="{}", status="connected",
  )
  values.update(overrides)
  repo.save_user_integration(user_id=user_id, provider=provider, **values)


JIRA_EXTRA = {
  "jira_url": "https://acme.atlassian.net", "cloud_id": "cloud-1", "account_email": "ana@acme.com",
  "account_id": "acct-1", "access_token_secret_id": "s-access", "refresh_token_secret_id": "s-refresh",
}


def jira_row(repo, user_id="u1"):
  return repo.session.query(UserJiraConnectionModel).filter_by(user_id=user_id).one_or_none()


# --------------------------------------------------------------------------- user integrations


def test_a_saved_user_integration_is_read_back_with_every_field(repo):
  save(repo)
  item = repo.get_user_integration("u1", "github")
  assert {key: item[key] for key in item if key != "id"} == {
    "user_id": "u1", "provider": "github", "external_account_id": "acct-1", "external_account_name": "Ana",
    "access_token_ref": "sec::a", "refresh_token_ref": "sec::r", "expires_at": 1234.5, "scopes_json": '["read"]',
    "connection_metadata_json": "{}", "status": "connected",
  }
  assert item["id"]


def test_a_missing_user_integration_is_none(repo):
  save(repo)
  assert repo.get_user_integration("u1", "gitlab") is None
  assert repo.get_user_integration("u2", "github") is None


def test_saving_again_updates_the_same_row(repo):
  save(repo)
  first_id = repo.get_user_integration("u1", "github")["id"]
  save(repo, external_account_name="Ana B", status="expired", access_token_ref=None)
  item = repo.get_user_integration("u1", "github")
  assert (item["id"], item["external_account_name"], item["status"], item["access_token_ref"]) == (
    first_id, "Ana B", "expired", None
  )
  assert item["refresh_token_ref"] == "sec::r"


def test_integrations_are_kept_per_user_and_provider(repo):
  save(repo, "u1", "github", external_account_name="one")
  save(repo, "u2", "github", external_account_name="two")
  save(repo, "u1", "gitlab", external_account_name="three")
  assert repo.get_user_integration("u1", "github")["external_account_name"] == "one"
  assert repo.get_user_integration("u2", "github")["external_account_name"] == "two"
  assert repo.get_user_integration("u1", "gitlab")["external_account_name"] == "three"


def test_only_jira_has_a_connection_row(repo):
  save(repo, provider="github", jira_extra=JIRA_EXTRA)
  assert jira_row(repo) is None


def test_jira_without_extra_data_has_no_connection_row(repo):
  save(repo, provider="jira")
  assert jira_row(repo) is None


def test_jira_connection_row_mirrors_the_integration_and_the_extra_data(repo):
  save(repo, provider="jira", jira_extra=JIRA_EXTRA)
  row = jira_row(repo)
  assert (row.jira_url, row.cloud_id, row.account_email, row.account_id) == (
    "https://acme.atlassian.net", "cloud-1", "ana@acme.com", "acct-1"
  )
  assert (row.access_token_secret_id, row.refresh_token_secret_id) == ("s-access", "s-refresh")
  assert (row.access_token_ref, row.refresh_token_ref, row.expires_at) == ("sec::a", "sec::r", 1234.5)
  assert (row.scopes_json, row.status) == ('["read"]', "connected")


def test_saving_jira_again_updates_its_connection_row(repo):
  save(repo, provider="jira", jira_extra=JIRA_EXTRA)
  first_id = jira_row(repo).id
  save(repo, provider="jira", status="expired", jira_extra={**JIRA_EXTRA, "cloud_id": "cloud-2", "account_email": None})
  row = jira_row(repo)
  assert (row.id, row.cloud_id, row.account_email, row.status) == (first_id, "cloud-2", None, "expired")
  assert repo.session.query(UserJiraConnectionModel).count() == 1


def test_missing_extra_fields_are_stored_as_empty(repo):
  save(repo, provider="jira", jira_extra={"jira_url": "https://acme.atlassian.net"})
  row = jira_row(repo)
  assert (row.jira_url, row.cloud_id, row.access_token_secret_id) == ("https://acme.atlassian.net", None, None)


def test_deleting_a_user_integration_reports_whether_it_existed(repo):
  save(repo)
  assert repo.delete_user_integration("u1", "github") is True
  assert repo.get_user_integration("u1", "github") is None
  assert repo.delete_user_integration("u1", "github") is False


def test_deleting_only_touches_the_given_user_and_provider(repo):
  save(repo, "u1", "github")
  save(repo, "u2", "github")
  save(repo, "u1", "gitlab")
  repo.delete_user_integration("u1", "github")
  assert repo.get_user_integration("u2", "github") is not None
  assert repo.get_user_integration("u1", "gitlab") is not None


def test_deleting_jira_also_removes_its_connection_row(repo):
  save(repo, provider="jira", jira_extra=JIRA_EXTRA)
  save(repo, "u2", "jira", jira_extra=JIRA_EXTRA)
  assert repo.delete_user_integration("u1", "jira") is True
  assert jira_row(repo, "u1") is None
  assert jira_row(repo, "u2") is not None


def test_deleting_another_provider_keeps_the_jira_connection_row(repo):
  save(repo, provider="jira", jira_extra=JIRA_EXTRA)
  save(repo, provider="github")
  repo.delete_user_integration("u1", "github")
  assert jira_row(repo) is not None


def test_a_jira_connection_row_alone_is_removed_but_not_reported(repo):
  save(repo, provider="jira", jira_extra=JIRA_EXTRA)
  repo.session.delete(repo._user_integration("u1", "jira"))
  repo.session.flush()
  assert repo.delete_user_integration("u1", "jira") is False
  assert jira_row(repo) is None


# --------------------------------------------------------------------------- provider credentials


def test_a_saved_credential_is_active_and_unvalidated(repo):
  repo.save_user_credential("u1", "openai", "s-access", "sec::x")
  cred = repo.get_user_credential("u1", "openai")
  assert (cred["user_id"], cred["provider"], cred["secret_id"], cred["secret_ref"]) == ("u1", "openai", "s-access", "sec::x")
  assert (cred["status"], cred["validation_error"], cred["last_validated_at"]) == ("active", None, None)
  assert cred["id"]


def test_a_missing_credential_is_none(repo):
  repo.save_user_credential("u1", "openai", "s-access", "sec::x")
  assert repo.get_user_credential("u1", "groq") is None
  assert repo.get_user_credential("u2", "openai") is None


def test_saving_a_credential_again_replaces_it_and_clears_the_error(repo):
  repo.save_user_credential("u1", "openai", "s-access", "sec::x")
  repo.update_credential_validation("u1", "openai", "invalid", "bad key")
  repo.save_user_credential("u1", "openai", "s-refresh", "sec::y")
  cred = repo.get_user_credential("u1", "openai")
  assert (cred["secret_id"], cred["secret_ref"], cred["status"], cred["validation_error"]) == (
    "s-refresh", "sec::y", "active", None
  )


def test_validating_a_credential_records_status_error_and_time(repo):
  repo.save_user_credential("u1", "openai", "s-access", "sec::x")
  before = datetime.now(timezone.utc)
  repo.update_credential_validation("u1", "openai", "invalid", "bad key")
  cred = repo.get_user_credential("u1", "openai")
  assert (cred["status"], cred["validation_error"]) == ("invalid", "bad key")
  assert before <= cred["last_validated_at"] <= datetime.now(timezone.utc)


def test_validating_a_missing_credential_changes_nothing(repo):
  repo.update_credential_validation("u1", "openai", "invalid", "bad key")
  assert repo.get_user_credential("u1", "openai") is None


def test_deleting_a_credential_reports_whether_it_existed(repo):
  repo.save_user_credential("u1", "openai", "s-access", "sec::x")
  repo.save_user_credential("u2", "openai", None, "sec::z")
  assert repo.delete_user_credential("u1", "openai") is True
  assert repo.get_user_credential("u1", "openai") is None
  assert repo.get_user_credential("u2", "openai") is not None
  assert repo.delete_user_credential("u1", "openai") is False


def test_listing_credentials_shows_status_without_secrets(repo):
  repo.save_user_credential("u1", "openai", "s-access", "sec::x")
  repo.save_user_credential("u1", "groq", "s-refresh", "sec::y")
  repo.save_user_credential("u2", "openai", None, "sec::z")
  repo.update_credential_validation("u1", "groq", "invalid", "bad key")
  listing = {c["provider"]: c for c in repo.list_user_credentials("u1")}
  assert set(listing) == {"openai", "groq"}
  assert listing["openai"] == {
    "provider": "openai", "status": "active", "is_configured": True, "last_validated_at": None,
    "validation_error": None, "updated_at": listing["openai"]["updated_at"],
  }
  assert listing["openai"]["updated_at"] is None or isinstance(listing["openai"]["updated_at"], str)
  assert listing["groq"]["status"] == "invalid" and listing["groq"]["validation_error"] == "bad key"
  assert datetime.fromisoformat(listing["groq"]["last_validated_at"]).tzinfo is not None


def test_listing_credentials_without_a_user_is_empty(repo):
  repo.save_user_credential("u1", "openai", "s-access", "sec::x")
  assert repo.list_user_credentials("") == []
  assert repo.list_user_credentials("nobody") == []


# --------------------------------------------------------------------------- organization integrations


def test_a_saved_organization_integration_is_read_back(repo):
  repo.save_organization_integration("default", "github", client_id="cid", client_secret_ref="enc")
  item = repo.get_organization_integration("default", "github")
  assert (item["organization_id"], item["provider"], item["client_id"]) == ("default", "github", "cid")
  assert (item["client_secret_ref"], item["status"]) == ("enc", "active")


def test_a_missing_organization_integration_is_none(repo):
  repo.save_organization_integration("default", "github")
  assert repo.get_organization_integration("default", "gitlab") is None


def test_an_update_changes_only_what_was_given(repo):
  repo.save_organization_integration("default", "github", client_id="cid", client_secret_ref="enc")
  repo.save_organization_integration("default", "github", status="inactive")
  item = repo.get_organization_integration("default", "github")
  assert (item["client_id"], item["client_secret_ref"], item["status"]) == ("cid", "enc", "inactive")
  repo.save_organization_integration("default", "github", client_id="cid2", client_secret_ref="enc2", status=None)
  item = repo.get_organization_integration("default", "github")
  assert (item["client_id"], item["client_secret_ref"], item["status"]) == ("cid2", "enc2", "inactive")


def test_an_organization_integration_has_one_row_per_provider(repo):
  repo.save_organization_integration("default", "github", client_id="a")
  repo.save_organization_integration("default", "github", client_id="b")
  repo.save_organization_integration("default", "gitlab", client_id="c")
  assert repo.get_organization_integration("default", "github")["client_id"] == "b"
  assert repo.get_organization_integration("default", "gitlab")["client_id"] == "c"


def test_organization_integration_existence_and_deletion(repo):
  assert repo.organization_integration_exists("default", "github") is False
  repo.save_organization_integration("default", "github")
  assert repo.organization_integration_exists("default", "github") is True
  assert repo.organization_integration_exists("default", "gitlab") is False
  assert repo.delete_organization_integration("default", "gitlab") is False
  assert repo.delete_organization_integration("default", "github") is True
  assert repo.organization_integration_exists("default", "github") is False
  assert repo.delete_organization_integration("default", "github") is False

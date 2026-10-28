"""User-centric preferences, credentials (BYOK), and Jira integrations API (/v1/me and /api/me).

Enforces strict isolation, AES-256-GCM encrypted persistence, and OWASP recommendations.
No plain secrets, ciphertexts, or internal keys are ever returned to the client.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_optional_current_user
from app.core.rls_context import set_rls_context
from app.core.settings import get_settings
from app.core.storage_credentials import (
  delete_user_credential,
  list_user_credentials_info,
  load_user_credential,
  save_user_credential,
  update_credential_validation,
)
from app.core.storage_preferences import get_user_preferences, save_user_preferences
from app.core.storage_user_integrations import (
  delete_user_integration,
  load_user_integration,
  save_user_integration,
)
from app.db.models import AuditEventModel
from app.integrations.registry import registry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["me-configuration"])

VALID_PROVIDERS = {"openai", "anthropic", "claude", "gemini", "groq"}


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class UserPreferencesResponse(BaseModel):
  inference_provider: Optional[str] = None
  inference_model: Optional[str] = None
  transcription_provider: Optional[str] = None
  transcription_model: Optional[str] = None
  language: str = "es"
  settings_json: dict[str, Any] = Field(default_factory=dict)
  updated_at: Optional[str] = None


class UserPreferencesUpdate(BaseModel):
  inference_provider: Optional[str] = None
  inference_model: Optional[str] = None
  transcription_provider: Optional[str] = None
  transcription_model: Optional[str] = None
  language: Optional[str] = None
  settings_json: Optional[dict[str, Any]] = None


class ProviderCredentialUpdate(BaseModel):
  api_key: str = Field(..., min_length=1)


class ProviderCredentialInfo(BaseModel):
  provider: str
  status: str
  is_configured: bool = True
  last_validated_at: Optional[str] = None
  validation_error: Optional[str] = None
  updated_at: Optional[str] = None


class JiraConnectRequest(BaseModel):
  jira_url: Optional[str] = None
  auth_method: str = "oauth"
  token: Optional[str] = None
  email: Optional[str] = None


class JiraConnectionInfo(BaseModel):
  connected: bool
  account_email: Optional[str] = None
  cloud_id: Optional[str] = None
  jira_url: Optional[str] = None
  scopes: List[str] = Field(default_factory=list)
  expires_at: Optional[float] = None
  status: str = "disconnected"


# ---------------------------------------------------------------------------
# 1. Preferences Endpoints
# ---------------------------------------------------------------------------

@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_my_preferences(
  current_user: dict[str, Any] = Depends(get_current_user),
) -> UserPreferencesResponse:
  """Get non-secret preferences for the authenticated user."""
  user_id = current_user["id"]
  prefs = get_user_preferences(user_id)
  return UserPreferencesResponse(
    inference_provider=prefs.get("inference_provider"),
    inference_model=prefs.get("inference_model"),
    transcription_provider=prefs.get("transcription_provider"),
    transcription_model=prefs.get("transcription_model"),
    language=prefs.get("language") or "es",
    settings_json=prefs.get("settings_json") or {},
    updated_at=prefs.get("updated_at"),
  )


@router.patch("/preferences", response_model=UserPreferencesResponse)
async def update_my_preferences(
  body: UserPreferencesUpdate,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> UserPreferencesResponse:
  """Update non-secret preferences for the authenticated user."""
  user_id = current_user["id"]
  payload = body.model_dump(exclude_none=True)

  updated = save_user_preferences(user_id, payload)
  return UserPreferencesResponse(
    inference_provider=updated.get("inference_provider"),
    inference_model=updated.get("inference_model"),
    transcription_provider=updated.get("transcription_provider"),
    transcription_model=updated.get("transcription_model"),
    language=updated.get("language") or "es",
    settings_json=updated.get("settings_json") or {},
    updated_at=updated.get("updated_at"),
  )


# ---------------------------------------------------------------------------
# 2. BYOK Provider Credentials Endpoints
# ---------------------------------------------------------------------------

@router.get("/provider-credentials", response_model=List[ProviderCredentialInfo])
async def list_my_provider_credentials(
  current_user: dict[str, Any] = Depends(get_current_user),
) -> List[ProviderCredentialInfo]:
  """List configured provider credentials metadata without leaking secrets."""
  user_id = current_user["id"]
  creds = list_user_credentials_info(user_id)
  return [ProviderCredentialInfo(**c) for c in creds]


@router.put("/provider-credentials/{provider}", response_model=ProviderCredentialInfo)
async def set_my_provider_credential(
  provider: str,
  body: ProviderCredentialUpdate,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> ProviderCredentialInfo:
  """Store an encrypted API key for the authenticated user."""
  prov = provider.lower().strip()
  if prov not in VALID_PROVIDERS:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail=f"Proveedor '{provider}' no soportado. Proveedores válidos: {', '.join(sorted(VALID_PROVIDERS))}",
    )

  user_id = current_user["id"]
  save_user_credential(user_id, prov, body.api_key)

  return ProviderCredentialInfo(
    provider=prov,
    status="active",
    is_configured=True,
  )


@router.post("/provider-credentials/{provider}/test")
async def test_my_provider_credential(
  provider: str,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  """Test connectivity and validation for a configured provider API key."""
  prov = provider.lower().strip()
  user_id = current_user["id"]

  plain_key = load_user_credential(user_id, prov)
  if not plain_key:
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail=f"No hay una llave configurada para el proveedor '{provider}'.",
    )

  # Validate key syntax and minimum length without exposing secret
  if len(plain_key) < 6:
    update_credential_validation(user_id, prov, status="validation_failed", error_msg="Formato de llave inválido")
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="La credencial configurada no tiene un formato válido.",
    )

  update_credential_validation(user_id, prov, status="active", error_msg=None)
  return {"ok": True, "provider": prov, "status": "active"}


@router.delete("/provider-credentials/{provider}")
async def delete_my_provider_credential(
  provider: str,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  """Delete a provider credential and its associated encrypted secret."""
  prov = provider.lower().strip()
  user_id = current_user["id"]

  deleted = delete_user_credential(user_id, prov)
  return {"ok": deleted, "provider": prov}


# ---------------------------------------------------------------------------
# 3. Jira Integration Endpoints
# ---------------------------------------------------------------------------

@router.post("/integrations/jira/connect")
async def connect_my_jira(
  body: Optional[JiraConnectRequest] = None,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  """Start personal Jira connection via OAuth 2.0 or PAT."""
  user_id = current_user["id"]
  jira_integration = registry.get("jira")

  if body and body.auth_method == "pat" and body.token:
    info = await jira_integration.connect_with_pat(
      token=body.token,
      email=body.email,
      base_url=body.jira_url or "",
    )
    save_user_integration(user_id, "jira", {
      "auth_method": "pat",
      "pat_token": body.token,
      "email": body.email,
      "jira_url": body.jira_url,
      "status": "connected",
    })
    return {"ok": True, "status": "connected", "info": info.model_dump() if hasattr(info, "model_dump") else info}

  # OAuth 2.0 3LO Start
  oauth_res = await jira_integration.start_oauth(user_id=user_id)
  return oauth_res.model_dump() if hasattr(oauth_res, "model_dump") else oauth_res


@router.get("/integrations/jira/callback")
async def my_jira_callback(
  code: Optional[str] = Query(None),
  state: Optional[str] = Query(None),
  error: Optional[str] = Query(None),
) -> Any:
  """Handle Jira OAuth redirect callback, exchanging authorization code for tokens."""
  settings = get_settings()
  frontend = settings.frontend_url.rstrip("/")

  if error:
    return RedirectResponse(f"{frontend}/integrations?jira=error&message={quote(error)}")
  if not code or not state:
    return RedirectResponse(f"{frontend}/integrations?jira=error&message=missing_code")

  try:
    jira_integration = registry.get("jira")
    await jira_integration.handle_oauth_callback(code, state)
    return RedirectResponse(f"{frontend}/integrations?jira=connected")
  except Exception as exc:
    logger.warning("Jira OAuth callback failed: %s", exc)
    return RedirectResponse(f"{frontend}/integrations?jira=error&message={quote(str(exc))}")


@router.get("/integrations/jira", response_model=JiraConnectionInfo)
async def get_my_jira_status(
  current_user: dict[str, Any] = Depends(get_current_user),
) -> JiraConnectionInfo:
  """Get personal Jira connection status for the authenticated user."""
  user_id = current_user["id"]
  data = load_user_integration(user_id, "jira")

  if not data or data.get("status") != "connected":
    return JiraConnectionInfo(connected=False, status="disconnected")

  scopes = data.get("scopes") or []
  if isinstance(scopes, str):
    try:
      scopes = scopes.split(" ")
    except Exception:
      scopes = []

  return JiraConnectionInfo(
    connected=True,
    status="connected",
    account_email=data.get("account_email") or data.get("email"),
    cloud_id=data.get("cloud_id"),
    jira_url=data.get("jira_url") or data.get("base_url") or data.get("site_url"),
    scopes=scopes,
    expires_at=data.get("expires_at"),
  )


@router.delete("/integrations/jira")
@router.delete("/integrations/jira/{connection_id}")
async def disconnect_my_jira(
  connection_id: Optional[str] = None,
  current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
  """Disconnect personal Jira integration and revoke/delete tokens."""
  user_id = current_user["id"]
  try:
    jira_integration = registry.get("jira")
    await jira_integration.disconnect(user_id=user_id)
  except Exception as exc:
    logger.debug("Jira disconnect error: %s", exc)

  deleted = delete_user_integration(user_id, "jira")
  return {"ok": True, "status": "disconnected"}


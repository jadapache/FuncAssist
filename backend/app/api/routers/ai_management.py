from typing import Any
import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from app.ai.endpoint_security import validate_remote_endpoint_url
from app.ai.providers.base import AIMessage
from app.ai.providers.factory import get_ai_settings, resolve_provider
from app.ai.providers.registry import FORBIDDEN_BACKEND_PROVIDERS
from app.api.deps import get_current_user
from app.api.middleware.error_handlers import handle_grounded_errors

router = APIRouter(
    prefix="/ai",
    tags=["ai-management"],
    dependencies=[Depends(get_current_user)],
)


class AITestConnectionRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    groq_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    claude_api_key: str | None = None
    ollama_base_url: str | None = None


AITestConnectionRequest.model_rebuild()


def _extract_candidate_api_key(body: AITestConnectionRequest) -> str | None:
    return (
        body.api_key
        or body.groq_api_key
        or body.openai_api_key
        or body.gemini_api_key
        or body.claude_api_key
    )


@router.post("/test-connection")
@handle_grounded_errors
async def test_ai_connection(
    body: AITestConnectionRequest = Body(...),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = current_user["id"]
    config = get_ai_settings(user_id=user_id)
    provider_name = (body.provider or config.get("provider") or "").lower()
    model_name = (body.model or config.get("model") or "").strip()

    if not provider_name:
        return {"ok": False, "message": "No hay ningún proveedor de IA configurado en el sistema."}

    if provider_name in FORBIDDEN_BACKEND_PROVIDERS:
        return {
            "ok": False,
            "message": "Los modelos de navegador se ejecutan y prueban exclusivamente en el cliente mediante WebLLM.",
            "provider": provider_name,
            "model": model_name,
        }

    if not model_name:
        return {"ok": False, "message": f"No hay un modelo especificado para el proveedor '{provider_name}'."}

    api_key = _extract_candidate_api_key(body)
    test_messages = [AIMessage(role="user", content="Hola, responde únicamente con la palabra 'OK'.")]

    try:
        p = resolve_provider(
            provider_name=provider_name,
            model_name=model_name,
            api_key=api_key,
            base_url=body.ollama_base_url,
            user_id=user_id,
        )
        res = await p.complete(test_messages, model=model_name, max_tokens=100)

        return {
            "ok": True,
            "message": f"Conexión exitosa con {provider_name} ({model_name}).",
            "response": res.text,
            "provider": provider_name,
            "model": model_name,
        }
    except Exception as e:
        return {
            "ok": False,
            "message": f"Error al probar conexión con {provider_name} ({model_name}): {e}",
            "provider": provider_name,
            "model": model_name,
        }


@router.get("/ollama/models")
@handle_grounded_errors
async def list_ollama_models(base_url: str | None = None) -> dict[str, Any]:
    config = get_ai_settings()
    raw_url = base_url or config.get("ollama_base_url") or ""
    target_url = raw_url.rstrip("/")

    if not target_url:
        return {"ok": False, "models": [], "message": "Debes configurar una URL explícita de Ollama remoto."}

    ok, err = validate_remote_endpoint_url(target_url)
    if not ok:
        return {"online": False, "models": [], "error": err}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(f"{target_url}/api/tags")
            res.raise_for_status()
            data = res.json()
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            return {"online": True, "models": models}
    except Exception as e:
        return {"online": False, "models": [], "error": str(e)}

import asyncio
from typing import Any, Optional
import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from app.ai.providers.base import AIMessage
from app.ai.providers.factory import get_ai_settings, resolve_provider
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


class OllamaPullRequest(BaseModel):
    name: str = Field(min_length=1)
    base_url: str | None = None


OllamaPullRequest.model_rebuild()


def _extract_candidate_api_key(body: AITestConnectionRequest) -> str | None:
    return (
        body.api_key
        or body.groq_api_key
        or body.openai_api_key
        or body.gemini_api_key
        or body.claude_api_key
    )


def _verify_builtin_model(model_name: str) -> dict[str, Any]:
    meta = resolve_model_meta(model_name)
    if not meta:
        return {
            "ok": False,
            "message": f"Modelo integrado '{model_name}' no reconocido en el catálogo.",
        }
    cache_dir = get_builtin_cache_dir()
    target_file = cache_dir / meta["filename"]
    if not target_file.exists() or target_file.stat().st_size < 10 * 1024 * 1024:
        return {
            "ok": False,
            "message": (
                f"El modelo local '{meta['name']}' no está descargado todavía en disco. "
                "Haz clic en el botón 'Descargar' en la sección de Modelos Integrados para instalarlo."
            ),
        }
    disk_size = round(target_file.stat().st_size / (1024 * 1024), 1)
    return {
        "ok": True,
        "message": f"Modelo integrado '{meta['name']}' verificado en disco ({disk_size} MB) y listo para uso local.",
        "provider": "builtin",
        "model": meta["id"],
    }


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
    target_url = (base_url or config.get("ollama_base_url") or "").rstrip("/")
    if not target_url:
        return {"ok": False, "message": "Debes configurar una URL explícita de Ollama."}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(f"{target_url}/api/tags")
            res.raise_for_status()
            data = res.json()
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            return {"online": True, "models": models}
    except Exception as e:
        return {"online": False, "models": [], "error": str(e)}


@router.post("/ollama/pull")
@handle_grounded_errors
async def pull_ollama_model(body: OllamaPullRequest = Body(...)) -> dict[str, Any]:
    config = get_ai_settings()
    target_url = (body.base_url or config.get("ollama_base_url") or "").rstrip("/")
    if not target_url:
        raise HTTPException(status_code=400, detail="Debes configurar una URL explícita de Ollama.")
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            res = await client.post(f"{target_url}/api/pull", json={"name": body.name, "stream": False})
            res.raise_for_status()
            return {"status": "success", "model": body.name, "response": res.json()}
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo conectar con Ollama en {target_url}. Verifica que Ollama esté instalado y ejecutándose en segundo plano (ej. ejecuta 'ollama serve' o abre la app de Ollama).",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al descargar el modelo {body.name} en Ollama: {e}")


@router.delete("/ollama/{model_name:path}")
@handle_grounded_errors
async def delete_ollama_model_endpoint(model_name: str, base_url: str | None = None) -> dict[str, Any]:
    """Delete a local Ollama model to free disk space."""
    config = get_ai_settings()
    target_url = (base_url or config.get("ollama_base_url") or "").rstrip("/")
    if not target_url:
        raise HTTPException(status_code=400, detail="Debes configurar una URL explícita de Ollama.")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            req = client.build_request("DELETE", f"{target_url}/api/delete", json={"name": model_name})
            res = await client.send(req)
            res.raise_for_status()
            return {"ok": True, "model": model_name, "message": f"Modelo {model_name} eliminado de Ollama correctamente."}
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo conectar con Ollama en {target_url}. Verifica que Ollama esté instalado y ejecutándose en segundo plano.",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar el modelo {model_name} en Ollama: {e}")

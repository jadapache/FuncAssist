import asyncio
from typing import Any
import httpx
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from app.ai.providers.base import AIMessage
from app.ai.providers.factory import get_ai_settings, resolve_provider
from app.api.middleware.error_handlers import handle_grounded_errors
from app.features.transcription.whisper_local import (
    cancel_whisper_download,
    delete_model_file,
    download_model_file,
    get_active_whisper_downloads,
    get_local_models_info,
)
from app.ai.builtin_local import (
    cancel_builtin_model_download,
    delete_builtin_model_file,
    download_builtin_model_file,
    get_active_downloads_status,
    get_builtin_cache_dir,
    get_builtin_models_info,
    resolve_model_meta,
)

router = APIRouter(prefix="/ai", tags=["ai-management"])


class AITestConnectionRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    ollama_base_url: str | None = None


AITestConnectionRequest.model_rebuild()


class OllamaPullRequest(BaseModel):
    name: str = Field(min_length=1)
    base_url: str | None = None


OllamaPullRequest.model_rebuild()


@router.post("/test-connection")
@handle_grounded_errors
async def test_ai_connection(body: AITestConnectionRequest = Body(...)) -> dict[str, Any]:
    config = get_ai_settings()
    provider_name = (body.provider or config.get("provider") or "").lower()
    model_name = (body.model or config.get("model") or "").strip()
    if not provider_name:
        return {
            "ok": False,
            "message": "No hay ningún proveedor de IA configurado en el sistema.",
        }
    if not model_name:
        return {
            "ok": False,
            "message": f"No hay un modelo especificado para el proveedor '{provider_name}'.",
        }

    if provider_name == "builtin":
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

    test_messages = [AIMessage(role="user", content="Hola, responde únicamente con la palabra 'OK'.")]

    try:
        p = resolve_provider(
            provider_name=provider_name,
            model_name=model_name,
            api_key=body.api_key,
            base_url=body.ollama_base_url,
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
    target_url = (base_url or config.get("ollama_base_url") or "http://127.0.0.1:11434").rstrip("/")
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
    target_url = (body.base_url or config.get("ollama_base_url") or "http://127.0.0.1:11434").rstrip("/")
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
    target_url = (base_url or config.get("ollama_base_url") or "http://127.0.0.1:11434").rstrip("/")
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


@router.get("/whisper/models")
@handle_grounded_errors
async def list_whisper_models() -> dict[str, Any]:
    """List all local Whisper built-in models and their download status on disk."""
    models = get_local_models_info()
    return {"ok": True, "models": models}


@router.post("/whisper/download/{model_id}")
@handle_grounded_errors
async def download_whisper_model_endpoint(model_id: str) -> dict[str, Any]:
    """Download a local Whisper model to disk cache."""
    try:
        clean_id = model_id.replace("whisper-", "")
        path = await asyncio.to_thread(download_model_file, clean_id)
        return {
            "ok": True,
            "model_id": clean_id,
            "file_path": str(path),
            "message": f"Modelo {clean_id} descargado y listo para uso local.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error descargando modelo Whisper {model_id}: {exc}") from exc


@router.delete("/whisper/{model_id}")
@handle_grounded_errors
async def delete_whisper_model_endpoint(model_id: str) -> dict[str, Any]:
    """Delete a downloaded local Whisper model from disk to free space."""
    try:
        clean_id = model_id.replace("whisper-", "")
        deleted = delete_model_file(clean_id)
        if not deleted:
            return {"ok": True, "message": f"El modelo {clean_id} no estaba descargado."}
        return {"ok": True, "message": f"Modelo Whisper {clean_id} eliminado del disco con éxito."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error eliminando modelo Whisper {model_id}: {exc}") from exc


@router.get("/builtin/models")
@handle_grounded_errors
async def list_builtin_models() -> dict[str, Any]:
    """List all local built-in LLM models and their download status on disk (without Ollama)."""
    models = get_builtin_models_info()
    return {"ok": True, "models": models}


@router.get("/builtin/tasks")
@handle_grounded_errors
async def get_builtin_download_tasks() -> dict[str, Any]:
    """Get active download tasks and progress for all built-in models (LLMs and Whisper)."""
    llm_tasks = get_active_downloads_status()
    whisper_tasks = get_active_whisper_downloads()
    return {"ok": True, "tasks": llm_tasks + whisper_tasks}


@router.post("/builtin/cancel/{model_id:path}")
@handle_grounded_errors
async def cancel_builtin_model_endpoint(model_id: str) -> dict[str, Any]:
    """Cancel an ongoing download of a built-in model (LLM or Whisper)."""
    cancelled = cancel_builtin_model_download(model_id)
    if not cancelled:
        cancelled = cancel_whisper_download(model_id)
    return {
        "ok": cancelled,
        "model_id": model_id,
        "message": "Descarga cancelada correctamente." if cancelled else "No se encontró una descarga activa para cancelar.",
    }



@router.post("/builtin/download/{model_id:path}")
@handle_grounded_errors
async def download_builtin_model_endpoint(model_id: str) -> dict[str, Any]:
    """Download a local built-in LLM model directly from Hugging Face into disk cache without Ollama."""
    try:
        path = await asyncio.to_thread(download_builtin_model_file, model_id)
        return {
            "ok": True,
            "model_id": model_id,
            "file_path": str(path),
            "message": f"Modelo {model_id} descargado y listo para uso local.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error descargando modelo built-in {model_id}: {exc}") from exc



@router.delete("/builtin/{model_id:path}")
@handle_grounded_errors
async def delete_builtin_model_endpoint(model_id: str) -> dict[str, Any]:
    """Delete a downloaded local built-in LLM model from disk to free space."""
    try:
        deleted = delete_builtin_model_file(model_id)
        if not deleted:
            return {"ok": True, "message": f"El modelo {model_id} no estaba descargado."}
        return {"ok": True, "message": f"Modelo {model_id} eliminado del disco con éxito."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error eliminando modelo built-in {model_id}: {exc}") from exc




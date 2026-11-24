# Capa LLM: configuración, rutas y observabilidad

Referencia de `backend/app/ai/**` y del chat agéntico (`/api/doc-agent/agentic-prompt-stream`).

## Variables de entorno

| Variable | Valor por defecto | Efecto |
|---|---|---|
| `AI_PROVIDER` / `AI_MODEL` | — | Proveedor y modelo principal si el usuario no configuró uno. |
| `OPENROUTER_API_KEY` / `DEEPSEEK_API_KEY` | — | Claves de OpenRouter y DeepSeek cuando el usuario no guardó una propia. El resto de proveedores usa `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` y `GROQ_API_KEY`. |
| `AI_FAST_MODEL` | elegido del catálogo | Modelo del tier rápido (planificación, resúmenes, map-reduce). |
| `AI_FALLBACK_MODELS` | — | Lista separada por comas, máximo 3, del mismo proveedor. Se prueban en orden si el principal falla. |
| `AI_PROMPT_CACHE` | `on` | `off` desactiva los puntos de caché explícitos (Anthropic). OpenAI, Gemini y DeepSeek cachean el prefijo de forma implícita. |
| `AI_AGENT_MODE` | `false` | `true` activa el bucle de herramientas cuando el modelo admite tool calling (`litellm.supports_function_calling`). Si no lo admite se usa la ruta normal. |
| `AI_AGENT_MAX_ITERS` | `8` | Iteraciones máximas del bucle de herramientas. |
| `AI_SECTION_GENERATION` | `true` | Generación por secciones para intents de documento cuando hay plan. |
| `AI_MAP_CONCURRENCY` | `2` (Groq) / `4` | Llamadas paralelas al condensar documentos (map-reduce). |
| `AI_TIMEOUT_S` | `60` (`120` en streaming) | Timeout por llamada al proveedor. |
| `AI_NUM_RETRIES` | `2` | Reintentos con backoff, **solo** para errores transitorios (429, timeout, 5xx, conexión). Los errores permanentes (modelo inexistente, autenticación, petición inválida) no se reintentan. |
| `AI_LLM_INTENT_CLASSIFIER` | `on` | Clasifica con el modelo rápido los mensajes que las reglas no deciden (ver más abajo). `off` usa solo reglas. |
| `AI_INTENT_CLASSIFIER_TIMEOUT_S` | `4` | Tiempo máximo de esa clasificación; si se agota se mantiene el resultado de las reglas. |
| `APP_VERSION` / `APP_BUILD_ID` | — | Se exponen en `/api/health` como `build`. |

La configuración por usuario (`PUT /api/ai/settings`) tiene prioridad sobre las variables. `fast_model` y `fallback_models` se validan contra el catálogo del proveedor; al cambiar de proveedor, los valores guardados que no existan en el nuevo se limpian.

## Selección de modelos

Los modelos por defecto salen del catálogo sincronizado (`frontier_sync` → tabla `ai_models_catalog`), no de constantes:

- Tier principal: modelo pedido → modelo configurado → `catalog.pick_model(provider, "main")` → valor del registro.
- Tier rápido: `fast_model` configurado → `catalog.pick_model(provider, "fast")` → modelo principal.
- `pick_model` recorre una lista ordenada de patrones por proveedor (por ejemplo `haiku` para Claude, `gpt-oss-20b` para Groq) y, entre las coincidencias, elige la versión más reciente sin fecha. Si el catálogo del proveedor está vacío usa el valor del registro; si tiene modelos pero ninguno coincide, el tier rápido usa el principal.
- Si el modelo rápido responde `model_not_found`, la llamada se repite una vez con el principal y se registra un warning.
- El modelo y los ajustes del usuario solo se aplican si la petición usa su proveedor configurado.

## Rutas del chat

`run_agentic_chat_stream` elige una ruta y la registra en el log (`route`):

| Ruta | Cuándo | Notas |
|---|---|---|
| `agent` | `AI_AGENT_MODE=true` y el modelo admite herramientas | Respuesta en streaming; los deltas de `tool_calls` se acumulan por índice. |
| `sections` | Intent de documento y el modelo rápido produjo un plan | Cada sección recibe historial e imágenes. Una sección que falla se reintenta una vez; si vuelve a fallar queda marcada como pendiente en el documento y se avisa en el `<chat>`. |
| `plain` | En el resto de casos | Si `finish_reason == "length"` o el artefacto quedó abierto, continúa (1 vez para `chat`, 2 para documentos). Si sigue cortada, añade un aviso al usuario. |

Topes de salida por intent en `ai/policies.py` (`chat`/`qna`: 4096; documentos: 8192). El tope efectivo lo limita `resolve_model_max_tokens` según el modelo.

### Clasificación del intent

1. Reglas (`classify_prompt_intent_by_rules`): modo explícito, comandos `/plan`, `/informe`..., seguimientos y palabras clave. Un mensaje como "regenera", "el documento está vacío" o "complétalo" en una conversación con artefacto activo conserva el intent de ese artefacto (guardado en `artifacts_json[].intent`), aunque esté formulado como pregunta.
2. Modelo rápido (`ai/intent_classifier.py`), solo si las reglas no decidieron (el mensaje cayó en el "chat" por defecto, o es una pregunta con un documento activo) **y** el mensaje parece tratar de un documento (hay artefacto activo o menciona documento, plan, informe, matriz, sección...). La charla corriente no paga la llamada extra. El resultado se guarda en caché por mensaje (512 entradas en memoria).

El log registra `intent_source` (`rules`, `model`, `model_cache`), `intent_rules` cuando el modelo cambió la decisión de las reglas e `intent_classifier_ms`.

## Cancelación

El endpoint de streaming consume el runner en una tarea aparte (`ai/stream_control.py`) y comprueba cada 0,5 s si el usuario canceló (`/runs/{id}/cancel`) o cerró la pestaña, también mientras espera al modelo, a una herramienta o a las secciones. Al detenerse se cancela la tarea, se cancelan las secciones pendientes y se cierra el stream de LiteLLM.

## Protocolo SSE

`POST /api/doc-agent/agentic-prompt-stream?protocol=v2` (el que usa el frontend) emite eventos con nombre:

| Evento | Datos |
|---|---|
| `status` | `{message, stage, ...}`. El primero trae `intent`, `run_id` y `conversation_id`. En la ruta por secciones, uno por sección con `section_index` y `pending`. |
| `plan` | `{title, extension, sections: [títulos]}` |
| `delta` | `{text}`: texto de chat, sin etiquetas `<chat>` |
| `artifact_start` / `artifact_delta` / `artifact_end` | `{index, title, extension}` / `{index, text}` / `{index, title, extension, truncated}` |
| `tool_call` / `tool_result` | Herramientas del modo agente |
| `usage` | Tokens, coste, `ttft_ms`, `duration_ms`, `finish_reason`, `continuations`, `route` |
| `error` | `{code, message, retry_after}`; `code` es el de `AIError` (`rate_limit`, `model_not_found`, `auth_error`, `timeout`, `cancelled`, ...) |
| `done` | Respuesta completa: `answer`, `assistant_message`, `artifacts`, `intent_detected`, `route`, `truncated`, `rubric_score`... |

`protocol=v1` (por defecto) se mantiene para pestañas con el bundle anterior en caché. Cada entrada del log guarda `protocol` (`v1`, `v2` o `json` para el endpoint sin streaming) y `/api/ai/logs/stats` muestra su distribución en `protocols`: v1 se puede retirar cuando deje de aparecer durante un ciclo de despliegue completo.

Ambos contratos están definidos en `app/schemas/agent_events.py`: `AgentEvent` (v2) y `RunEventEnvelope` (v1).

## Logs y métricas

Cada petición al chat deja una entrada en `USER_DATA_DIR/ai/logs/AAAA-MM-DD.jsonl`, termine bien, falle o se cancele, con `route`, `intent`, `provider`, `model`, `fast_model`, uso de tokens, `finish_reason`, `continuations` y, si falla, `error_code`, `error_message`, `error_detail` y `stage`.

`GET /api/ai/logs/stats?limit=N` devuelve totales de tokens y coste, p50/p95 de duración y TTFT, `fallback_rate`, `cache_hit_rate` (`cached_tokens / prompt_tokens`), `error_rate`, `truncation_rate` y la distribución por ruta. `list_logs` lee cada archivo desde el final.

## Pruebas contra proveedores reales

`python -m scripts.smoke_ai_providers` (desde `backend/`) muestra, sin llamar a ningún proveedor, qué modelo principal y rápido resuelve el catálogo para cada proveedor y avisa si los valores del registro ya no están en el catálogo.

Con `--live` (consume crédito) y las claves configuradas, por proveedor: una llamada del tier rápido (indicando si tuvo que recurrir al modelo principal), un plan por secciones (debe dar `sections > 0`) y, si el modelo admite herramientas, una llamada a herramienta en streaming seguida de la respuesta final. `--providers groq,claude,openai` limita los proveedores (también acepta `openrouter` y `deepseek`, que no están en la lista por defecto) y `--user <id>` usa las claves guardadas de ese usuario. Sale con código 1 si alguna comprobación falla.

## Datos

- **Resumen de historial**: columnas `history_summary`, `history_summary_key` y `history_summary_updated_at` en `chat_sessions`. La migración se aplica al arrancar; para aplicarla antes del despliegue: `python -m scripts.migrate_chat_history_summary` (`--rollback` para revertir).
- **Duplicados históricos de mensajes**: `python -m scripts.dedupe_chat_messages` lista los mensajes consecutivos de la misma sesión con igual rol y contenido creados con menos de 10 s de diferencia (`--session <prefijo>`, `--window <s>`). Con `--apply` los borra, conservando la primera copia.
- `save_session` solo sobrescribe `artifacts_json` y `document_content` cuando la petición los incluye: un turno de chat sin documento ya no borra los artefactos guardados.

## Caché del frontend

nginx sirve `index.html` con `Cache-Control: no-cache` y `/assets/*` (nombres con hash) con caché de un año: al recargar la página el navegador siempre obtiene el bundle desplegado. Para las pestañas abiertas durante un despliegue, `NewVersionAlert` compara cada 5 minutos, y al recuperar el foco, el bundle que está ejecutando con el que referencia el `index.html` del servidor; si cambió, pide recargar. El backend mantiene el protocolo SSE v1 para quien no recargue.

## Modelos de redacción en el navegador (WebLLM)

Código: `frontend/src/features/ai/` (`providers/WebLLMProvider.ts`, `services/InferenceService.ts`) y `frontend/src/core/gpu/gpuResources.ts`.

- **Ventana de contexto**: WebLLM carga los modelos del catálogo con 4.096 tokens (los valores de VRAM del catálogo corresponden a ese tamaño). El motor se crea con `context_window_size` explícito y cada petición se ajusta a esa ventana (`utils/promptBudget.ts`): si no cabe, se recorta por el medio el mensaje más largo, conservando el principio y el final, y se limita la respuesta (como máximo la mitad de la ventana). Las continuaciones solo reenvían el final de la respuesta.
- **Un modelo en la GPU a la vez**: antes de cargar WebLLM se pide a Whisper del navegador que libere la GPU, y al revés antes de transcribir en el navegador. El worker de Whisper se libera solo tras 2 minutos sin trabajos, y WebLLM tras 10 minutos sin uso.
- **Una pestaña a la vez**: el modelo se carga con un Web Lock (`funcassist-webllm-gpu`); otra pestaña recibe un aviso en lugar de cargar una segunda copia. Sin HTTPS no hay Web Locks y no se coordina.
- **Modelo que no cabe**: tras un error de memoria o un reinicio de la GPU, se reintenta una vez con Llama 3.2 1B, se avisa con un toast y se recuerda en el navegador (`localStorage`) que ese modelo no cabe en el equipo; Configuración lo marca. Cargarlo de nuevo con éxito desde Configuración borra la marca.
- **Errores**: `errors/browserLlmErrors.ts` distingue sin HTTPS (`insecure_context`), sin WebGPU, GPU no compatible, falta de memoria, reinicio de la GPU por tiempo (`DXGI_ERROR_DEVICE_HUNG`), GPU perdida, texto demasiado largo y otra pestaña usando el modelo. El error original se registra en la consola del navegador con el prefijo `[WebLLM]`.
- **HTTPS**: fuera de `localhost` los modelos del navegador necesitan HTTPS. Ver [DEPLOY_HTTPS.md](./DEPLOY_HTTPS.md).

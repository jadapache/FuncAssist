# Plan de correcciones pendientes: capa LLM agéntica

> Estado: propuesta para revisión · Fecha: 2026-11-20 · Rama: `feat-agentic-mode`
> Alcance: `backend/app/ai/**`, `backend/app/api/document_agent.py`, cliente de chat del frontend.

Este plan recoge lo detectado al probar en el contenedor los cambios de la rama. Cada punto incluye la evidencia, la causa, la corrección propuesta y el criterio de aceptación.

## Resumen

| # | Prioridad | Problema | Impacto |
|---|---|---|---|
| 1 | P0 | Modelos por defecto y modelo rápido inexistentes en Groq y Claude | Generación por secciones, map-reduce y resumen de historial fallan en silencio |
| 2 | P0 | Tope de 1500 tokens en intent `chat` | Documentos pedidos en un turno conversacional salen cortados y en el chat |
| 3 | P0 | Errores silenciados y fallos de stream sin registro | Fallos invisibles; diagnóstico difícil |
| 4 | P1 | Seguimientos como "regenera" o "está vacío" no se reconocen como petición de artefacto | El modelo responde en el chat en vez de regenerar el artefacto |
| 5 | P1 | Frontend en caché incompatible con el backend nuevo | Fallo inmediato del stream y mensajes duplicados hasta recargar |
| 6 | P1 | Generación por secciones incompleta | Ignora historial e imágenes, errores dentro del documento |
| 7 | P1 | Modo agente: soporte de herramientas sin verificar y sin streaming | Errores con modelos sin tool calling; respuesta poco fluida |
| 8 | P1 | Cancelación parcial al desconectarse el cliente | Tokens consumidos tras cerrar la pestaña |
| 9 | P2 | Flujos grounded: continuación duplicada y `max_tokens` fijo | Deuda técnica |
| 10 | P2 | Clasificación de errores por subcadenas amplias | Errores mal clasificados |
| 11 | P2 | SSE v2 sin completar | La interfaz no muestra estado, herramientas ni uso |
| 12 | P2 | Configuración sin `fallback_models` ni `fast_model` en la UI | Solo configurables por API o variables de entorno |
| 13 | P2 | Métricas y logs incompletos | Sin p50/p95, tasa de respaldo ni tasa de aciertos de caché |
| 14 | P2 | Commit después de responder en endpoints sin streaming | Fallos de commit invisibles para el cliente |
| 15 | P2 | Datos y documentación | Duplicados históricos y documentación desactualizada |

---

## P0: bloqueantes

### 1. Modelos por defecto y modelo rápido inexistentes

**Evidencia**
- Llamada directa al modelo rápido de Groq desde el contenedor: `NotFoundError: The model llama-3.1-8b-instant does not exist or you do not have access to it`. LiteLLM además lo reintentó 2 veces.
- Comparación del registro con el catálogo persistido:

| Proveedor | `default_model` | ¿En catálogo? | `fast_model` | ¿En catálogo? |
|---|---|---|---|---|
| groq | `llama-3.3-70b-versatile` | No | `llama-3.1-8b-instant` | No |
| claude | `claude-3-5-sonnet-latest` | No | `claude-3-5-haiku-latest` | No |
| openai | `gpt-4o` | Sí | `gpt-4o-mini` | Sí |
| gemini | `gemini-2.5-flash` | Sí | `gemini-2.5-flash` | Sí |

**Causa**
Los modelos están fijados en `providers/registry.py` mientras el catálogo se sincroniza dinámicamente con `frontier_sync`. Cuando el usuario no configura `fast_model`, se usa el valor fijado, que ya no existe. Los consumidores del modelo rápido atrapan la excepción sin registrarla:
- `section_generator.plan_document` devuelve `None`, así que la generación por secciones **nunca** se activa.
- `map_reduce_condense_context` recorta cada fragmento a 1200 caracteres en lugar de resumirlo.
- `prune_or_summarize_history` descarta los turnos antiguos sin resumirlos.

**Corrección propuesta**
1. Resolver el modelo rápido y el principal por defecto desde el catálogo, no desde constantes:
   - Nuevo `catalog.pick_model(provider, tier)` que elige, entre los modelos de chat del proveedor presentes en el catálogo, el preferido por tier mediante una lista ordenada de patrones (por ejemplo `haiku`, `mini`, `flash-lite`, `gpt-oss-20b` para el tier rápido). Los valores del registro pasan a ser solo la última opción.
   - Si no hay coincidencia, el tier rápido usa el modelo principal del usuario.
2. Respaldo en tiempo de ejecución: si una llamada del tier rápido falla con `model_not_found`, repetir una vez con el modelo principal y registrar un warning.
3. No reintentar errores permanentes: excluir `NotFoundError`, `AuthenticationError` y `BadRequestError` de `num_retries` (usar el `retry_policy` de LiteLLM o capturar antes de reintentar).
4. Validar `fast_model` y `fallback_models` contra el catálogo al guardar la configuración (`PUT /ai/settings`), igual que ya se hace con los modelos de WebLLM.
5. Actualizar los valores del registro para Groq y Claude a modelos presentes en el catálogo.

**Archivos**: `ai/catalog.py`, `ai/providers/registry.py`, `ai/providers/factory.py`, `ai/providers/implementations.py`, `api/routers/ai_settings.py`.

**Tests**
- `pick_model` elige el modelo rápido preferido presente en el catálogo y cae al principal cuando no hay ninguno.
- Una llamada del tier rápido con `model_not_found` reintenta con el principal.
- Los errores permanentes no se reintentan.

**Aceptación**: con la configuración actual de Groq, "genera un plan de pruebas" produce `sections > 0` en el log de IA.

### 2. Tope de 1500 tokens en el intent `chat`

**Evidencia**: log del 2026-11-20 22:35:30. `intent: chat`, `completion_tokens: 1500` exactos y documento en Markdown cortado en `| Rol | Nombre | Firma | Fecha |`.

**Causa**: `policies.INTENT_MAX_TOKENS["chat"] = 1500`, aplicado en la ruta conversacional desde los cambios de presupuesto. Antes todas las peticiones usaban 8192.

**Corrección propuesta**
1. Subir `chat` y `qna` a 4096. El tope real lo sigue imponiendo `resolve_model_max_tokens` según el modelo.
2. Detectar `finish_reason == "length"` en la ruta conversacional y continuar una vez con `continue_if_truncated`. Si sigue cortada, añadir un aviso al usuario en lugar de terminar en silencio.
3. Registrar `finish_reason` en el log de IA.

**Archivos**: `ai/policies.py`, `ai/runner.py`, `ai/providers/implementations.py` (exponer `finish_reason` también en streaming).

**Aceptación**: una respuesta conversacional larga no termina en exactamente el tope de tokens sin continuación ni aviso.

### 3. Errores silenciados y fallos de stream sin registro

**Evidencia**: la petición de las 22:35:13 respondió 1194 bytes en menos de un segundo, con un error enviado por SSE, y no dejó entrada en `ai/logs`. Los fallos del tier rápido (punto 1) tampoco dejan rastro.

**Corrección propuesta**
1. Añadir `logger.warning(..., exc_info=True)` en todos los `except Exception` de `section_generator`, `map_reduce`, `history` y `tools`.
2. En `document_agent.py`, ante una excepción del stream, llamar a `log_ai_call` con `error_code`, `error_message`, `intent` y `stage`.
3. `log_ai_call`: guardar la referencia de la tarea de escritura en un `set` global y descartarla al terminar (`task.add_done_callback`), para que no se pierdan entradas.
4. Registrar la ruta usada (`route: agent | sections | plain`) en cada entrada.

**Aceptación**: cualquier petición al chat, termine bien o mal, deja una entrada en el log con su ruta y, si falla, con el error.

---

## P1: importantes

### 4. Seguimientos que piden regenerar el artefacto

**Evidencia**: "El documento está vacío" se clasificó como `chat`. Con la regla conversacional, que prohíbe `<artifact>`, el modelo escribió el documento dentro del chat.

**Corrección propuesta**
- En `classify_prompt_intent`, si la conversación tiene un artefacto activo y el mensaje pide regenerar, corregir o completar el documento (por ejemplo "regenera", "está vacío", "complétalo", "corrige el documento"), clasificar con el intent del artefacto activo.
- Pasar a la clasificación los artefactos de la sesión, que ya existen en `chat_sessions.artifacts_json`.
- Valorar una clasificación con el modelo rápido cuando las reglas no decidan, con el resultado guardado en caché por mensaje.

**Aceptación**: tras generar un artefacto, "regenera" o "el documento está vacío" produce un nuevo bloque `<artifact>`.

### 5. Compatibilidad entre frontend en caché y backend

**Evidencia**: hasta recargar la página, la pestaña siguió ejecutando el JavaScript anterior al rebuild. Consecuencias: mensajes duplicados (sin `userMessageId`) y un fallo inmediato del stream de causa no identificada.

**Corrección propuesta**
1. Servir `index.html` con `Cache-Control: no-cache` en nginx. Los assets con hash pueden seguir con caché larga.
2. Exponer la versión de la app en `/api/health` y comprobarla desde el frontend al recuperar el foco o cada N minutos. Si cambió, mostrar un aviso "Hay una nueva versión, recarga".
3. Reproducir el fallo de 1194 bytes con el bundle anterior para confirmar que solo era incompatibilidad y no un error del backend.

**Archivos**: `docker/nginx/server-common.conf` (antes `docker/nginx.conf`), endpoint de salud, frontend.

### 6. Generación por secciones (una vez resuelto el punto 1)

- Incluir el historial y las imágenes en las llamadas de cada sección.
- Si una sección falla, no escribir el error dentro del documento: reintentarla una vez y, si vuelve a fallar, avisar en el `<chat>` y dejar la sección marcada como pendiente.
- Emitir un evento `plan` con las secciones previstas, para que la interfaz muestre el progreso.
- Cancelar las tareas pendientes si el cliente se desconecta.

### 7. Modo agente

- Calcular `supports_tools` con `litellm.supports_function_calling(model)` en lugar de suponer `True` para todos los proveedores. Si no hay soporte, usar la ruta normal.
- Respuesta incremental: usar `complete_stream` con tool calls y acumular los deltas de `tool_calls`.
- Probar con `AI_AGENT_MODE=on` en Claude, OpenAI y un modelo de Groq con tool calling.

### 8. Cancelación al desconectarse

- Comprobar la desconexión también durante el ciclo del agente y la generación por secciones, no solo entre chunks.
- Cancelar explícitamente las tareas en curso (`asyncio.Task.cancel`) y cerrar el stream de LiteLLM.

---

## P2: mejoras

### 9. Flujos grounded
- Usar `continue_if_truncated` en `run_grounded_feature` y en su versión de streaming, eliminando las dos copias de la lógica de continuación.
- Sustituir `GROUNDED_MAX_TOKENS = 8192` fijo por la política por intent o feature.

### 10. Clasificación de errores
- Sustituir las subcadenas `"auth"`, `"timeout"` y `"429"` por comprobaciones de tipo (`isinstance`) y códigos de estado HTTP del error de LiteLLM.

### 11. SSE v2 de punta a punta
- Emitir `status`, `plan`, `usage` y `artifact_start`/`artifact_delta` también en la ruta normal y en la de secciones.
- Unificar `app/ai/events.py` con `app/schemas/agent_events.py`, que hoy definen dos `AgentEvent`.
- Adaptar el cliente (`docAgentApi.agenticPromptStream`) a v2 y retirar v1 cuando no tenga consumidores.

### 12. Pantalla de configuración
- Campos para `fast_model` y hasta 3 `fallback_models`, con selector alimentado por el catálogo del proveedor activo.

### 13. Métricas y logs
- `/ai/logs/stats`: p50/p95 de duración y TTFT, tasa de respaldo, tasa de aciertos de caché (`cached_tokens / prompt_tokens`), distribución por ruta.
- `list_logs`: leer desde el final del archivo en vez de cargarlo completo.

### 14. Commit después de responder
- Evaluar `Depends(get_db_session, scope="function")` para los endpoints sin streaming, de modo que un fallo de commit devuelva error al cliente. Las rutas de streaming mantienen `scope="request"`.

### 15. Datos y documentación
- Script de limpieza de duplicados históricos en `chat_messages` (mismo `session_id`, rol y contenido, consecutivos y creados con menos de 10 s de diferencia), con modo de prueba antes de borrar. Caso conocido: conversación `cbff759a`.
- Documentar las variables nuevas (`AI_PROMPT_CACHE`, `AI_FALLBACK_MODELS`, `AI_FAST_MODEL`, `AI_AGENT_MODE`, `AI_AGENT_MAX_ITERS`, `AI_SECTION_GENERATION`, `AI_MAP_CONCURRENCY`, `AI_TIMEOUT_S`, `AI_NUM_RETRIES`) y la migración del resumen de historial.

---

## Ya validado en el contenedor

- La migración `history_summary*` está aplicada en PostgreSQL.
- Con el frontend actualizado, los mensajes se guardan sin duplicados (turnos posteriores a las 22:43).
- La generación de artefactos con plantilla (`template_mutation`) funciona con y sin historial.

## Estado de implementación (2026-11-20)

Implementado en la rama; **pendiente de ejecutar los tests y validar en el contenedor** (no se pudieron ejecutar en el equipo de desarrollo).

| # | Estado | Notas |
|---|---|---|
| 1 | Hecho | `catalog.pick_model`, respaldo `model_not_found` → modelo principal (también en streaming), reintentos propios solo para errores transitorios (`num_retries=0` en LiteLLM), validación en `PUT /ai/settings`, registro actualizado. Aceptación en el entorno real: `python -m scripts.smoke_ai_providers --live --providers groq` (comprobación "section plan"). |
| 2 | Hecho | `chat`/`qna` a 4096, continuación por `finish_reason == "length"`, aviso si sigue cortada, `finish_reason` en el log. |
| 3 | Hecho | Warnings con `exc_info`, una entrada de log por petición (también fallos y cancelaciones) con `route` y `stage`, referencias a las tareas de escritura. |
| 4 | Hecho | Reglas para seguimientos con artefacto activo (intent guardado en `artifacts_json[].intent`) y clasificación con el modelo rápido, con caché por mensaje, solo para mensajes que las reglas no deciden y que tratan de un documento (`ai/intent_classifier.py`, `AI_LLM_INTENT_CLASSIFIER`). |
| 5 | Hecho (5.1, 5.2) | nginx `no-cache` en `index.html` y caché larga en `/assets/`; aviso de nueva versión (`NewVersionAlert`) comparando el bundle cargado con el de `index.html`; `build` en `/api/health`. 5.3 (reproducir el fallo de 1194 bytes) no se pudo hacer sin el bundle anterior; los fallos ahora quedan en el log. |
| 6 | Hecho | Historial e imágenes por sección, un reintento, sección pendiente en lugar del error, evento `plan`, cancelación de tareas. |
| 7 | Hecho (código) | `supports_function_calling`, streaming con acumulación de `tool_calls`. Prueba real pendiente de ejecutar con claves: `python -m scripts.smoke_ai_providers --live --providers groq,claude,openai`. |
| 8 | Hecho | Consumo en tarea aparte con sondeo de cancelación/desconexión cada 0,5 s; cierre del stream de LiteLLM. |
| 9 | Hecho | Lógica de continuación única; `GROUNDED_MAX_TOKENS` sustituido por `policies.resolve_feature_max_tokens`. |
| 10 | Hecho | Clasificación por tipo y código HTTP, también en `document_agent`. |
| 11 | Hecho | v2 en todas las rutas, un solo módulo de contratos (`AgentEvent` v2, `RunEventEnvelope` v1), cliente migrado a v2. v1 se mantiene por los bundles en caché; el log guarda `protocol` y `/api/ai/logs/stats` muestra la distribución para decidir cuándo retirarlo. |
| 12 | Hecho | Selector de modelo rápido y hasta 3 de respaldo, alimentado por el catálogo. |
| 13 | Hecho | p50/p95 de duración y TTFT, tasas de respaldo, caché, error y truncado, distribución por ruta; lectura desde el final. |
| 14 | Hecho | `scope="function"` en los repositorios y `scope="request"` en el streaming del chat; `requirements.txt` exige FastAPI ≥ 0.121. |
| 15 | Hecho (código) | `scripts/dedupe_chat_messages.py` (modo de prueba por defecto) y `docs/AI_LAYER.md`. Pendiente ejecutarlo contra la base de datos: primero `--session cbff759a`, luego `--apply`. |

## Orden de ejecución sugerido

1. Puntos 1, 3 y 2: desbloquean la generación por secciones y hacen visibles los fallos.
2. Punto 4: experiencia de regenerar artefactos.
3. Punto 5: evita repetir el problema de caché en cada despliegue.
4. Puntos 6, 7 y 8.
5. Puntos 9 a 15.

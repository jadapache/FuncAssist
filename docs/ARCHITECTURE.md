# Arquitectura del Sistema — FuncAssist

Guía del diseño, patrones y decisiones arquitectónicas de FuncAssist (v0.8.0).

---

## 📐 Visión General

```
┌──────────────────────────────────────────────────────────────────┐
│                    React 19 SPA (Vite + Tailwind v4)             │
│  pages/            Dashboard, Login                              │
│  features/         chat · document · knowledge · integrations ·  │
│                    settings · transcription · ai                 │
│  context/          Auth, User, Chat, BackgroundJob, Loading,     │
│                    Sidebar, Toast                                │
│  core/api          apiClient + config                            │
│  In-browser AI:    @mlc-ai/web-llm (WebGPU) · Whisper ONNX       │
│                    (@huggingface/transformers en Web Worker)     │
│  Editor visual:    Univer (docs + sheets)                        │
└──────────────────┬───────────────────────────────────────────────┘
                   │ REST / JSON + SSE (streaming)
┌──────────────────▼───────────────────────────────────────────────┐
│                    FastAPI Backend (app/)                        │
│  api/            Routers bajo /api                               │
│   ├─ auth, user, me (/me, /v1/me)                                │
│   ├─ routers/features_pm   (standup, ask, prd-checker,           │
│   │                         change-impact)                       │
│   ├─ routers/features_qa   (qa/{feature_key})                    │
│   ├─ routers/features_doc  (mejoras, inventario, levantamiento)  │
│   ├─ document_agent        (/doc-agent: agentic-prompt[-stream], │
│   │                         export-docx, export-xlsx)            │
│   ├─ knowledge, history, drafts, templates                       │
│   ├─ transcription, transcription_stream                         │
│   ├─ routers/ai_settings, ai_management, ai_templates            │
│   ├─ integrations, settings                                      │
│   └─ middleware/error_handlers                                   │
│  features/       standup, prd_checker, change_impact, mejoras,   │
│                  inventario, levantamiento, transcription, drafts│
│  services/       template_renderer (docx/xlsx), rubric_evaluator,│
│                  documents, event_serializer                     │
│  context/        RAG: builder, service, knowledge, retrieval,    │
│                  memory                                          │
│  ai/             runner, providers/, catalog, frontier_sync,     │
│                  templates, seeds, map_reduce, section_generator,│
│                  artifacts, endpoint_security, logging           │
│  integrations/   jira, github, gitlab + registry, executor, sync │
│  db/             models (SQLAlchemy), interfaces/, repositories/,│
│                  unit_of_work                                    │
│  core/           settings, security, secret_store, rls_context,  │
│                  redis, storage_*, migration, index_refresher    │
│  schemas/        Pydantic (chat, prd, standup, test_plan,        │
│                  transcription, artifacts/, agent_events)        │
└───────┬───────────────┬──────────────────┬───────────────────────┘
        ▼               ▼                  ▼
┌──────────────┐ ┌─────────────┐ ┌──────────────────────────────┐
│ PostgreSQL 16│ │  Valkey 8   │ │ Servicios externos           │
│ + pgvector   │ │ caché       │ │ Jira · GitHub · GitLab       │
│ RLS por      │ │ compartida  │ │ LLMs vía LiteLLM: OpenAI,    │
│ usuario/org  │ │             │ │ Anthropic, Gemini, Groq,     │
└──────────────┘ └─────────────┘ │ OpenRouter, DeepSeek,        │
                                 │ Ollama remoto · Servidores   │
                                 │ MCP                          │
                                 └──────────────────────────────┘
        + Volúmenes de archivos: DATA_DIR (settings, cache, generated,
          transcriptions) y KNOWLEDGE_DATA_DIR (documentos subidos)
```

### Despliegue

`compose.yaml` define cuatro servicios:

| Servicio   | Imagen                     | Rol |
|------------|----------------------------|-----|
| `frontend` | nginx con el build de Vite | Sirve la SPA y hace proxy a `/api` (puerto `APP_PORT`, 6728 por defecto) |
| `backend`  | `backend/Dockerfile`       | FastAPI/uvicorn en el puerto 8000, healthcheck en `/api/health` |
| `db`       | `pgvector/pgvector:0.8.7-pg16-bookworm`| Base de datos relacional + vectores |
| `valkey`   | `valkey/valkey:8.1.12-alpine` (AOF) | Caché compartida |
| `openbao` + `openbao-agent` | `openbao/openbao:2.7.3` | Gestión de secretos (SECRET_KEY, PBKDF2_SALT) |

Variables obligatorias: `POSTGRES_PASSWORD`. `SECRET_KEY` y `PBKDF2_SALT` se leen desde OpenBao (ver `SECURITY_COMPLIANCE.md`). El backend no arranca sin `DATABASE_URL` y `VALKEY_URL`. También existe `render.yaml` para despliegue en Render.

---

## 🏛️ Principios de Diseño

### 1. Separación de capas

- **HTTP** (`api/`): validación con Pydantic, autenticación, mapeo de errores (`middleware/error_handlers.py`).
- **Negocio** (`features/`, `services/`, `context/`, `ai/`): orquestación y lógica pura.
- **Datos** (`db/`): repositorios sobre SQLAlchemy async; sin SQL en los handlers.
- **Infraestructura** (`core/`): configuración, secretos, RLS, Valkey, almacenamiento en disco.

### 2. Inyección de dependencias

Los handlers reciben repositorios, usuario actual y sesión de BD vía `Depends()` (`api/deps.py`):

```python
async def ask_product(
    body: GroundedRequest,
    chat_repo: IChatRepository = Depends(get_chat_repository),
) -> dict[str, Any]: ...
```

### 3. Repository Pattern + Unit of Work

- **Interfaces** en `db/interfaces/` (`IUserRepository`, `ISettingsRepository`, `ISecretRepository`, `IIntegrationRepository`, `IMcpServerRepository`, `ITemplateRepository`, `ICorporateTemplateRepository`, `ICatalogRepository`, `ITranscriptionRepository`, `IOrganizationRepository`).
- **Implementaciones** en `db/repositories/` heredando de `BaseRepository`.
- **`AsyncUnitOfWork`** (`db/unit_of_work.py`) agrupa repositorios (chats, standups, PRD, test plans, etc.) en una sola transacción.
- `db/database.py` expone engines y sesiones async (`psycopg`) y sync, con overrides para tests.

### 4. Multi-tenant con Row-Level Security

`core/rls_context.py` fija por transacción `app.current_user_id` y `app.current_org_id`; las políticas RLS de PostgreSQL aíslan los datos entre usuarios y organizaciones (`organizations`, `organization_members`).

### 5. Abstracción de proveedores de IA

`ai/providers/` define el protocolo base, un registro y una factory; `implementations.py` envuelve LiteLLM. El proveedor activo se resuelve en tiempo de ejecución a partir de las credenciales y preferencias del usuario (`user_provider_credentials`, `user_preferences`). Cambiar de proveedor es configuración, no código.

### 6. Persistencia en servidor

Todo el estado de negocio (conversaciones, artefactos, resultados de features, transcripciones, configuración) se persiste en el backend. El navegador solo guarda en `localStorage`:

- el **token JWT** de sesión (`context/AuthContext.tsx`, `core/api/config.ts`);
- la referencia mínima de las **transcripciones en curso** (`{id, title, kind, startedAt}`, en `features/transcription/utils/transcriptionStorage.ts`); el estado real se pide a `GET /api/transcription/jobs/active` al iniciar sesión.

---

## 🤖 Arquitectura de IA y frontera de ejecución

FuncAssist sigue un paradigma **Client-First** para la IA local:

1. **Ejecución en el navegador (sin pesos en el backend)**
   - **Chat/escritura local**: `@mlc-ai/web-llm` sobre WebGPU; los pesos quedan en la caché del navegador (Cache API / OPFS).
   - **Reconocimiento de voz local**: Whisper ONNX vía `@huggingface/transformers` en un Web Worker (WebGPU/WASM).
   - El backend no descarga, almacena ni ejecuta modelos GGUF, Whisper u ONNX.

2. **Proveedores cloud**
   - OpenAI, Anthropic, Google Gemini, Groq, OpenRouter y DeepSeek se invocan desde el backend vía LiteLLM con claves cifradas.
   - **Ollama remoto** se trata como API externa por HTTPS. `ai/endpoint_security.py` (y los validadores del frontend) rechazan loopback (`127.0.0.1`, `localhost`, `::1`) e IPs privadas.
   - La transcripción en servidor usa Groq u OpenAI (`features/transcription/whisper_cloud.py`) con fragmentación, recorte de silencios, limpieza de muletillas y diarización de OpenAI cuando hay clave. Detalle en [TRANSCRIPTION_PROCESS.md](./TRANSCRIPTION_PROCESS.md).

3. **Catálogo de modelos**
   - `ai/frontier_sync.py` sincroniza en segundo plano precios, ventanas de contexto y límites de salida desde la base de LiteLLM (con fallback offline) hacia `ai_models_catalog`.
   - `ai/map_reduce.py` calcula un presupuesto de caracteres por proveedor y divide entradas largas en chunks para evitar errores de límite de tokens.

4. **Plantillas de IA versionadas**
   - Prompts y rúbricas viven en BD (`ai_templates`, `ai_template_versions`), sembrados por `ai/seeds.py` y gestionados vía la API de `ai_templates`.
   - Plantillas corporativas DOCX/XLSX (`corporate_templates`) se renderizan con `services/template_renderer/`.

---

## 🔄 Flujos Principales

### Flujo 1: Feature “grounded” (p. ej. Standup)

```
1. POST /api/features/standup  {query, sources: ["jira","github"]}
2. Handler valida (Pydantic) y llama al runner
3. Runner:
   a) Carga la plantilla activa (prompt + rúbrica) desde ai_templates
   b) assemble_context(): integraciones + conocimiento → ContextChunks
   c) Si no hay contexto → refused = true
   d) Aplica presupuesto de contexto (map_reduce) según proveedor
   e) Resuelve proveedor y llama al LLM vía LiteLLM
   f) Evalúa con la rúbrica (rubric_evaluator) y registra la llamada (ai/logging)
4. Respuesta: {answer, answer_clean, artifacts, citations, meta}
5. Persistencia del resultado en BD (standups / chat_sessions / chat_messages)
```

Mismo patrón para `ask`, `prd-checker`, `change-impact` y `qa/{feature_key}`.

### Flujo 2: Agente de documentos (Mejoras / Inventario / Levantamiento)

```
1. Usuario adjunta documentos (parse-attachment) y escribe un prompt
2. POST /api/doc-agent/agentic-prompt-stream  (SSE)
3. Backend:
   a) Valida request y sesión
   b) Recupera contexto (chunks de los documentos + búsqueda híbrida)
   c) section_generator genera el documento por secciones contra el
      schema del artefacto (schemas/artifacts/*), validado por
      core/document_agent/validator
   d) Emite eventos (schemas/agent_events, event_serializer):
      pasos de razonamiento, secciones, artefactos
4. Frontend (features/document): muestra los pasos en vivo, actualiza
   artefactos y los renderiza en Univer; la conversación y sus artefactos
   se sincronizan con el backend (chatSessionsApi)
5. Cancelación: POST /runs/{run_id}/cancel o /sessions/{id}/cancel
6. Exportación: POST /export-docx | /export-xlsx (plantillas corporativas)
```

### Flujo 3: Integraciones (Jira / GitHub / GitLab)

```
1. Usuario conecta (OAuth para Jira, PAT para GitHub/GitLab)
2. Backend valida, cifra la credencial (SecretStore) y la guarda en
   user_integrations / user_jira_connections (o organization_integrations)
3. Sync (integrations/sync.py) obtiene issues, PRs, commits; caché en Valkey
4. En RAG, assemble_context(sources=[...]) consulta el adapter vía registry
   y devuelve ContextChunks con source_type = jira | github | gitlab
```

Los servidores MCP configurados por el usuario (`mcp_servers`) se invocan mediante `integrations/executor.py`.

### Flujo 4: Base de conocimiento

```
1. Upload (PDF/DOCX/TXT/MD) → archivo en KNOWLEDGE_DATA_DIR
2. Ingesta (context/knowledge.py): extracción → chunks en PostgreSQL
   con columna tsvector('spanish') generada y embedding (pgvector)
3. Búsqueda (context/retrieval.py):
   - Full-text: ts_rank_cd + websearch_to_tsquery('spanish')
   - Vectorial: distancia coseno (embedding <=> vector)
   - Fallback por trigramas (pg_trgm word_similarity, extensión obligatoria)
4. core/index_refresher mantiene el índice actualizado
```

---

## 💾 Modelo de Datos (PostgreSQL)

| Dominio | Tablas |
|---------|--------|
| Identidad y tenancy | `users`, `organizations`, `organization_members`, `audit_events` |
| Configuración | `settings`, `user_preferences` |
| Secretos | `user_secrets`, `user_provider_credentials` |
| Integraciones | `user_jira_connections`, `user_integrations`, `organization_integrations`, `mcp_servers` |
| Conversación | `chat_sessions`, `chat_messages` |
| Resultados de features | `standups`, `prd_reviews`, `test_plans`, `transcriptions` |
| IA | `ai_templates`, `ai_template_versions`, `ai_models_catalog` |
| Plantillas documentales | `corporate_templates` |
| Conocimiento | tablas de documentos/chunks (con `tsvector` y `embedding`) |

`ContextChunk` (`context/models.py`) es un objeto en memoria, no persistido:
`id, document_id, source_type, source_label, title, content, relevance_score`.

Las migraciones son manuales e idempotentes (`core/migration.py`, `context/knowledge_migration.py`, `core/integration_migration.py`), ejecutadas al arrancar; no se usa Alembic.

---

## 🔐 Seguridad

### Autenticación
- JWT firmado (HMAC-SHA256), expiración de 7 días, sin renovación automática.
- El token se guarda en `localStorage` del navegador (expuesto ante XSS; mitigable con CSP).
- Contraseñas con PBKDF2-HMAC (`PBKDF2_SALT`).

### Secretos
- `core/secret_store.py`: **AES-256-GCM** con nonce aleatorio de 96 bits y AAD por usuario y propósito; compatibilidad con tokens Fernet heredados.
- Clave derivada de `SECRET_KEY`. Las credenciales nunca se exponen al frontend.

### Aislamiento
- RLS de PostgreSQL por usuario/organización (`rls_context`).
- Validación SSRF de endpoints de IA (`endpoint_security`).
- Registro de auditoría en `audit_events`.

### Validación de entrada
- Esquemas Pydantic v2 estrictos con restricciones de campo.

---

## 🔌 Extensibilidad

### Nueva integración
1. `app/integrations/{service}/integration.py` extendiendo `IntegrationAdapter` (`integrations/base.py`).
2. Registrar en `integrations/registry.py`.
3. Endpoints en `api/integrations.py`.
4. UI en `frontend/src/features/integrations/`.

### Nuevo feature de IA
1. Sembrar la plantilla (prompt + rúbrica) en `ai/seeds.py` o crearla vía la API de plantillas.
2. Servicio en `app/features/{feature}/service.py`.
3. Endpoint en el router correspondiente (`features_pm`, `features_qa` o `features_doc`).
4. Si produce documento: schema en `schemas/artifacts/` y builder docx/xlsx.

### Nuevo proveedor de IA
1. Implementación en `ai/providers/implementations.py` y registro en `providers/registry.py`.
2. Entrada en `ai/catalog.py`.
3. UI en `frontend/src/features/settings/` y `features/ai/`.

---

## 📊 Frontend

Organización por features (`frontend/src/features/*`), cada una con `api/`, `components/`, `hooks/`, `pages/` y `types/` según aplique:

- **chat**: conversación grounded. `useChatPersistence` carga y guarda las sesiones en el backend vía `chatSessionsApi` (tablas `chat_sessions` / `chat_messages`); la sesión activa se refleja en la URL.
- **document**: workspace agéntico (`agent/`, `univer/`), artefactos, undo/redo, streaming de pasos.
- **knowledge**: gestión de documentos de conocimiento.
- **transcription**: grabación/subida, ASR local en Web Worker o cloud, jobs en segundo plano.
- **settings / ai**: proveedores, catálogos, políticas y validadores de endpoints.
- **integrations**: conexión y estado de Jira/GitHub/GitLab.

Estado global mediante Context API; trabajos largos notificados vía `BackgroundJobContext` + `FloatingJobToast`. Tests con Vitest.

---

## 🚀 Decisiones y Trade-offs

| Decisión | Razón | Trade-off |
|----------|-------|-----------|
| PostgreSQL + pgvector | Multi-usuario, RLS, FTS y vectores en un solo motor | Requiere servicio de BD |
| Búsqueda híbrida FTS + vector (+ fallback por trigramas) | Precisión léxica en español + semántica | Coste de embeddings e índices |
| Valkey | Caché compartida entre workers | Dependencia adicional obligatoria |
| LiteLLM | Una sola abstracción multi-proveedor | Acoplamiento a su catálogo |
| Persistencia en servidor (no en navegador) | Historial multi-dispositivo y aislado por tenant | Requiere conexión al backend |
| IA local en navegador | Privacidad, cero inferencia en servidor | Depende de WebGPU del cliente |
| Migraciones manuales | Simplicidad | Sin historial de versiones de esquema |

### Limitaciones conocidas
1. **Contexto del LLM**: entradas grandes se dividen (map-reduce), pero proveedores con límites bajos (p. ej. Groq) reducen la calidad.
2. **Streaming SSE**: puede degradarse con conexiones inestables.
3. **IA en navegador**: requiere hardware/navegador con WebGPU.

---

Para más detalle, consulta [BACKEND.md](./BACKEND.md) y [FRONTEND.md](./FRONTEND.md).

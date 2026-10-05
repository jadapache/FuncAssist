# Arquitectura del Sistema — QA Project MGMT

Guía completa del diseño, patrones y decisiones arquitectónicas de QA Project MGMT.

---

## 📐 Visión General

```
┌─────────────────────────────────────────────────────────────────┐
│                     React 19 SPA (Vite)                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Pages (Standup, PRD Checker, QA Features, Ask Product) │  │
│  │  Components (Settings, Integrations, Knowledge, Chat)   │  │
│  │  Hooks (useChatPersistence, useDocumentHistory, etc)    │  │
│  │  Context API (Auth, Toast)                              │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────┬──────────────────────────────────────────────┘
                   │ REST / JSON
┌──────────────────▼──────────────────────────────────────────────┐
│                    FastAPI Backend                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  HTTP Layer: app/api/ (routers REST)                   │   │
│  │  ├─ auth.py        (Login, Register, Profile)         │   │
│  │  ├─ features.py    (Standup, Ask, PRD, QA, Impact)    │   │
│  │  ├─ knowledge.py   (Document Upload, Retrieve)        │   │
│  │  ├─ integrations.py (Jira, GitHub, GitLab, Sync)     │   │
│  │  └─ doc_agent.py   (Agentic RAG, Document Mutations) │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Business Logic: features/, context/, db/               │   │
│  │  ├─ features/standup/service.py (Standup generation)  │   │
│  │  ├─ features/mejoras/docx_builder.py (Export)         │   │
│  │  ├─ context/service.py (RAG assembly)                 │   │
│  │  ├─ context/knowledge.py (Document ingestion)         │   │
│  │  ├─ context/retrieval.py (BM25 ranking)               │   │
│  │  ├─ db/repositories/ (Repository Pattern)             │   │
│  │  └─ integrations/{jira,github,gitlab}/ (Adapters)   │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  AI Engine: app/ai/                                    │   │
│  │  ├─ runner.py (Orchestrator: prompt → LLM → log)      │   │
│  │  ├─ artifacts.py (Parse múltiples artefactos XML)     │   │
│  │  ├─ providers/ (Multi-provider abstraction)           │   │
│  │  │  └─ implementations.py (LiteLLM wrapper)           │   │
│  │  ├─ templates.py (System prompts, rúbricas)          │   │
│  │  ├─ catalog.py (Model discovery)                      │   │
│  │  └─ logging.py (Auditoría)                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Infrastructure: core/, db/                            │   │
│  │  ├─ core/settings.py (Config management)              │   │
│  │  ├─ core/security.py (JWT, password hashing)          │   │
│  │  ├─ core/secrets.py (Fernet encryption for API keys)  │   │
│  │  ├─ core/storage.py (Local file I/O, credentials)     │   │
│  │  ├─ db/database.py (SQLite async pool)                │   │
│  │  └─ db/interfaces/ (Repository pattern abstractions)   │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────────────────┘
                   │
        ┌──────────┼──────────┬──────────┐
        ▼          ▼          ▼          ▼
    ┌────────┐ ┌────────┐ ┌──────────┐ ┌─────────┐
    │ Jira   │ │ GitHub │ │ GitLab   │ │ Ollama  │
    │ OAuth  │ │ PAT    │ │ PAT      │ │ Local   │
    │ Sync   │ │        │ │          │ │ OpenAI  │
    └────────┘ └────────┘ └──────────┘ │ Anthropic
                                        └─────────┘
        ▼          ▼          ▼
    ┌────────────────────────────────────────┐
    │  Local Storage (local/)                 │
    │  ├─ SQLite Database (users, chats)     │
    │  ├─ Knowledge Index (documents, BM25)  │
    │  ├─ AI Logs (audit trail)              │
    │  └─ Encrypted Credentials              │
    └────────────────────────────────────────┘
```

---

## 🏛️ Principios de Diseño

### 1. **Separación de Capas**

El sistema respeta la arquitectura por capas:

- **Capa HTTP**: Validación de entrada, conversión de tipos, error handling
- **Capa de Negocio**: Lógica pura, orquestación de servicios
- **Capa de Datos**: Repository pattern, acceso a BD via interfaces abstractas
- **Capa de Infraestructura**: Configuración, secrets, logging, storage

**Ventaja**: Cambios en una capa no rompen otras. Ejemplo: cambiar de SQLite a PostgreSQL solo afecta `db/repositories/`.

### 2. **Inyección de Dependencias**

FastAPI's `Depends()` y type hints aseguran que cada handler reciba lo que necesita:

```python
async def ask_product(
    body: GroundedRequest,
    chat_repo: IChatRepository = Depends(get_chat_repository),
) -> dict[str, Any]:
    # chat_repo es el repositorio concreto, inyectado automáticamente
```

**Ventaja**: Testeable, mockeable, composable.

### 3. **Repository Pattern para Acceso a Datos**

Cada entidad (User, Chat, Standup) tiene:
- **Interfaz abstracta**: `IUserRepository` → contrato que todos cumplen
- **Implementación concreta**: `UserRepository(BaseRepository)` → SQLite específico
- **Factory**: `get_user_repository()` → proveedor de dependencias

**Ventaja**: No hay SQL embebido en handlers. BD es intercambiable.

### 4. **Abstracción de Proveedores de IA**

Múltiples proveedores (Ollama, OpenAI, Anthropic) comparten interfaz:

```python
class AIProvider(Protocol):
    async def complete(messages: list[AIMessage]) -> AICompletion
    async def complete_stream(messages) -> AsyncGenerator[str]
```

Resolución dinámica: `resolve_provider()` → retorna el proveedor configurado actualmente.

**Ventaja**: Cambiar de Ollama a OpenAI es un cambio de configuración, no de código.

### 5. **Local-First Storage**

- **No requiere servidor externo**: Todo funciona offline (excepto integraciones)
- **Credenciales cifradas**: Fernet encryption con clave del sistema
- **SQLite para BD relacional**: Portable, embebido, sin dependencias
- **JSON para índices**: BM25 index serializado en JSON plano

**Ventaja**: Privacidad, portabilidad, desarrollo sin fricción.

---

## 🔄 Flujos Principales

### Flujo 1: Generación de Standup

```
1. Usuario: "Generate standup for today"
   ↓
2. API: POST /api/features/standup
   {query: "Generate standup", sources: ["jira", "github"]}
   ↓
3. Backend Handler:
   a) Validar request con Pydantic
   b) Llamar run_grounded_feature(feature="standup", ...)
   ↓
4. Runner:
   a) Obtener prompt de standup desde local/ai/prompts/standup.json
   b) Obtener rúbrica desde local/ai/rubrics/standup.json
   c) assemble_context():
      - Conectar a Jira → obtener issues de hoy
      - Conectar a GitHub → obtener PRs/commits
      - Convertir a ContextChunks
   d) Si contexto vacío → refused=true
   e) Resolver proveedor AI (ej: Ollama)
   f) Armar prompt user con template + contexto + rúbrica
   g) Llamar LLM con mensajes
   h) log_ai_call({...}) → escribe en local/ai/logs/{uuid}.json
   ↓
5. Response:
   {
     ok: true,
     answer: "# Daily Standup\n...",
     answer_clean: "# Daily Standup\n...",
     artifacts: [],
     citations: [{index: 1, source: "jira", title: "PROJ-123"}],
     meta: {provider: "ollama", model: "llama2", log_id: "..."}
   }
   ↓
6. Frontend:
   a) Recibe respuesta
   b) Renderiza markdown en UI
   c) Opción de copiar/descargar
   d) Guarda en localStorage (useChatPersistence)
```

### Flujo 2: Agentic RAG para Documento de Mejoras

```
1. Usuario en MejorasPage:
   - Carga documento (PDF/DOCX)
   - Escribe prompt: "Agrega análisis de riesgos"
   ↓
2. API: POST /api/doc-agent/agentic-prompt
   {
     query: "Agrega análisis de riesgos",
     document_ids: ["doc_123"],
     current_document: "# Documento...",
     chat_context: ["Contexto anterior..."]
   }
   ↓
3. Backend:
   a) Validar request + autenticación
   b) Detectar intención (por palabras clave):
      - "imagen/captura" → InspectImageOperation
      - "corregir/cambiar" → ReplaceContentOperation
      - "agregar responsable" → InsertTextOperation
      - Default → run_grounded_feature(feature="mejoras_doc", ...)
   c) Para el caso default (RAG):
      - assemble_context(query, sources)
      - chunks_from_documents(document_ids)
      - Ensamblar bundle
      - Llamar LLM
      - Parsear respuesta para múltiples artefactos (<artifact> tags)
   ↓
4. Response:
   {
     answer: "# Documento de Mejora\n<artifact title='Análisis de Riesgos'>...",
     answer_clean: "# Documento de Mejora\n...",
     artifacts: [
       {title: "Análisis de Riesgos", extension: "docx", content: "..."}
     ],
     operations: [InsertTextOperation, ...],
     document_updates: "# Documento actualizado..."
   }
   ↓
5. Frontend (AgenticDocumentWorkspace):
   a) Recibe respuesta
   b) Parsea res.artifacts (si el backend los retorna)
   c) Crea/actualiza artifacts en la conversación
   d) Renderiza en editor visual (Univer)
   e) Autosave a localStorage cada 1.5s
   ↓
6. Usuario:
   - Edita el documento en directo
   - Descarga como .docx (POST /api/doc-agent/export-docx)
   - Regenera con nuevo prompt
```

### Flujo 3: Sincronización de Integración (GitHub)

```
1. Usuario conecta GitHub con PAT:
   POST /api/integrations/github/pat
   {token: "ghp_...", selected_repos: ["repo1", "repo2"]}
   ↓
2. Backend:
   a) Valida PAT con GET /user
   b) Encripta credencial con Fernet
   c) Guarda en local/connections/github.enc
   d) Carga en registry singleton
   ↓
3. Sync (manual o automático):
   POST /api/integrations/github/sync
   ↓
4. GitHubAdapter:
   a) Obtiene PRs, commits, branches desde API
   b) Cachea en local/integrations/github_cache.json
   c) Retorna {repositories, pull_requests, commits}
   ↓
5. Uso en RAG:
   assemble_context("query", sources=["github"])
   → Llama adapter.get_pull_requests()
   → Retorna ContextChunks [{source_type: "github", ...}]
```

---

## 💾 Modelo de Datos

### Entidades Principales

```
UserProfile (en local/settings/app.json)
├─ display_name: str ("Juan Pérez")
├─ user_role: str ("admin" | "pm" | "funcional" | "dev" | "qa")
├─ theme: str ("command-center")
└─ ai: dict (Encrypted API keys and model choices)

ChatMessage (en local/history/chat_{session_id}.json)
├─ id: str (UUID)
├─ session_id: str
├─ role: str ("user" | "assistant")
├─ content: str
├─ context_sources: list[dict]
└─ created_at: str

Standup
├─ id: str (UUID)
├─ title: str
├─ content: str (Markdown)
├─ sources: list[str]
└─ created_at: str

PRDReview
├─ id: str (UUID)
├─ prd_title: str
├─ content: str (Markdown)
└─ created_at: str

KnowledgeDocument
├─ id: str (UUID)
├─ filename: str
├─ file_type: str (".pdf" | ".docx" | ".txt" | ".md")
├─ file_size: int
├─ tags: list[str]
├─ chunk_count: int
└─ uploaded_at: str

ContextChunk (en memoria, no persistido en DB)
├─ id: str
├─ document_id: str
├─ source_type: str ("knowledge" | "jira" | "github" | "gitlab")
├─ source_label: str (ej: "github/pull_requests")
├─ title: str
├─ content: str (segmento de texto)
└─ relevance_score: float (para BM25)
```

---

## 🔌 Extensibilidad

### Agregar Nueva Fuente de Integración

1. Crear `app/integrations/{service}/integration.py` con clase que extienda `IntegrationAdapter`
2. Implementar métodos abstractos: `authenticate()`, `test_connection()`, `get_capabilities()`
3. Registrar en `app/integrations/registry.py`
4. Crear endpoint en `app/api/integrations.py`
5. Agregar UI en `frontend/src/components/integrations/{service}Page.tsx`

### Agregar Nuevo Feature de IA

1. Crear prompt en `local/ai/prompts/{feature}.json`:
   ```json
   {
     "version": "1.0",
     "system": "You are a QA expert...",
     "user_template": "Analyze this:\n{context}\n\nRubric:\n{rubric}",
     "allowed_sources": ["knowledge", "jira", "github"]
   }
   ```
2. Crear rúbrica en `local/ai/rubrics/{feature}.json`
3. Crear endpoint en `app/api/features.py`: `@router.post("/features/{feature}")`
4. Llamar `run_grounded_feature(feature="{feature}", ...)`

### Agregar Nuevo Proveedor de IA

1. Crear clase en `app/ai/providers/implementations.py` heredando de `AIProvider`
2. Implementar `complete()` y `complete_stream()` async
3. Agregar entrada en `app/ai/catalog.py`
4. Actualizar UI en `frontend/src/pages/SettingsPage.tsx`

---

## 📊 Flujo de Estado en Frontend

### Arquitectura de Hooks

```
AgenticDocumentWorkspace (página principal)
├─ useChatPersistence(featureSlug)
│  ├─ conversations: ChatConversation[]
│  ├─ activeConversation: ChatConversation | null
│  ├─ createConversation(), updateConversation(), ...
│  └─ Persistencia en localStorage
├─ useArtifacts(conversationArtifacts, onUpdateConversation)
│  ├─ artifacts: Artifact[]
│  ├─ activeArtifact: Artifact | null
│  ├─ createArtifact(), deleteArtifact(), ...
│  └─ Gestión de múltiples documentos
├─ useDocumentHistory(activeArtifact?.content)
│  ├─ content: string
│  ├─ stack: string[] (undo/redo)
│  ├─ pushContent(), undo(), redo(), ...
│  └─ Undo/redo sin límite (hasta 100 estados)
└─ useAgenticGeneration({...})
   ├─ isGenerating: boolean
   ├─ liveThinkingSteps: ThinkingStep[]
   ├─ handleSendMessage(query)
   └─ Orquestación de generación AI + RAG

ArtifactsStudio (panel derecho)
├─ Recibe: artifacts, activeArtifactId
├─ Emite: onSelectArtifact, onCreate, onDelete, ...
└─ Renderiza: lista o editor visual (Univer)
```

---

## 🔐 Seguridad

### Autenticación

- **JWT Bearer tokens** con firma HMAC-SHA256
- **Expiración**: 7 días
- **Renovación**: No automática (requiere re-login)
- **Almacenamiento**: `localStorage` (vulnerable a XSS, pero con CSP headers mitigable)

### Credenciales de Integración

- **Encriptación**: Fernet (AES-128)
- **Clave**: Derivada de `PMQA_SECRET_KEY` (env) o `keyring` del sistema
- **Almacenamiento**: `local/connections/{service}.enc`
- **Acceso**: Solo backend, nunca expuesto al frontend

### Validación de Entrada

- **Pydantic schemas** con validación estricta
- **Type hints** para auto-documentación
- **Field constraints**: min/max length, regex patterns

---

## 🚀 Optimizaciones y Trade-offs

### Decisiones Tecnológicas

| Decisión | Razón | Trade-off |
|----------|-------|-----------|
| **SQLite** en lugar de PostgreSQL | Local-first, sin dependencias | No escalable a múltiples procesos |
| **BM25** en lugar de embeddings | Rápido, interpretable, offline | Menos semántico que LLMs |
| **LiteLLM** como wrapper | Multi-provider, single abstraction | Overhead mínimo |
| **localStorage** para persistencia frontend | Simple, offline | Limitado a 5-10 MB por origen |
| **JSON para índices** | Serializable, legible | Más lento que pickle binary |

### Limitaciones Conocidas

1. **Concurrencia**: FastAPI con `uvicorn` single-worker no es thread-safe en BD. Usar `gunicorn` con workers para producción.
2. **Escalabilidad de conocimiento**: BM25 con >100k chunks degrada en performance. Considerar Elasticsearch para producción.
3. **Contexto del LLM**: Limite de tokens del modelo. Si contexto + prompt > max_tokens, se rechaza.
4. **Streaming de artefactos**: En navegadores con internet lento, SSE puede degradarse.

---

## 📚 Referencias y Estándares

- **REST**: JSON:API-like patterns (pero no estricto)
- **Async**: `asyncio` en Python, promises en JavaScript
- **Type Safety**: Pydantic + TypeScript strict mode
- **CSS**: Tailwind CSS v4 con tokens personalizados
- **Database Migrations**: Manual (no Alembic) — migraciones en `db/database.py::init_db()`

---

¡Para más detalles, consulta [BACKEND.md](./BACKEND.md) y [FRONTEND.md](./FRONTEND.md)!

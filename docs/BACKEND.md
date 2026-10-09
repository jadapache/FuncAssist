# Backend — Especificación Técnica

Guía completa de módulos Python, endpoints FastAPI, y patrones utilizados en el backend de QA Project MGMT.

---

## 📂 Estructura de Módulos

```
backend/app/
├── ai/                          # Motor de generación con IA
│   ├── __init__.py
│   ├── runner.py               # Orquestador principal (run_grounded_feature)
│   ├── artifacts.py            # Parser de <artifact> tags XML
│   ├── templates.py            # Prompts y rúbricas (JSON)
│   ├── catalog.py              # Catálogo de modelos disponibles
│   ├── logging.py              # Auditoría de llamadas AI
│   └── providers/              # Abstracción de proveedores
│       ├── base.py            # Interfaz AIProvider
│       ├── factory.py         # Resolución de proveedor actual
│       ├── implementations.py # LiteLLMProvider (OpenAI, Claude, Ollama)
│       └── registry.py        # Especificación de modelos
│
├── api/                         # Routers HTTP FastAPI
│   ├── __init__.py
│   ├── router.py              # Composición de todos los routers
│   ├── deps.py                # Inyección de dependencias
│   ├── auth.py                # Login, registro, perfil
│   ├── features.py            # Endpoints de features QA/PM
│   ├── knowledge.py           # Upload de documentos, RAG
│   ├── document_agent.py      # Agentic RAG para documentos
│   ├── integrations.py        # Jira, GitHub, GitLab, sync
│   ├── settings.py            # Configuración, salud
│   └── history.py             # Historial de conversaciones
│
├── context/                     # RAG Engine (SQLite FTS5 + BM25)
│   ├── __init__.py
│   ├── models.py              # ContextChunk, ContextBundle
│   ├── knowledge.py           # Ingesta, chunking y almacenamiento SQLite FTS5
│   ├── knowledge_migration.py # Migración JSON->SQLite, export y recovery
│   ├── retrieval.py           # Búsqueda híbrida (FTS5 + BM25 fallback)
│   └── service.py             # Orquestación (assemble_context)
│
├── core/                        # Núcleo de infraestructura
│   ├── __init__.py
│   ├── settings.py            # Configuración (AppSettings)
│   ├── security.py            # JWT, hashing de contraseñas
│   ├── secrets.py             # Cifrado Fernet de API keys
│   ├── storage.py             # File I/O, credenciales
│   ├── integration_config.py  # Lectura/escritura de conexiones
│   ├── template_storage.py    # Gestión de plantillas corporativas
│   └── document_agent/        # Schema y validación para doc-agent
│       ├── schema.py          # Modelos canónicos
│       └── validator.py       # Validación de operaciones
│
├── db/                          # Capa de datos
│   ├── __init__.py
│   ├── database.py            # Conexión, init_db()
│   ├── base.py                # BaseRepository
│   ├── interfaces/            # Interfaces abstractas (I*)
│   │   ├── __init__.py
│   │   ├── user_repository.py
│   │   ├── chat_repository.py
│   │   ├── standup_repository.py
│   │   ├── prd_repository.py
│   │   └── test_plan_repository.py
│   └── repositories/          # Implementaciones concretas
│       ├── __init__.py
│       ├── base_repository.py
│       ├── user_repository.py
│       ├── chat_repository.py
│       ├── standup_repository.py
│       ├── prd_repository.py
│       └── test_plan_repository.py
│
├── features/                    # Servicios de feature
│   ├── __init__.py
│   ├── standup/
│   │   ├── __init__.py
│   │   └── service.py         # generate_standup()
│   └── mejoras/
│       ├── __init__.py
│       └── docx_builder.py    # create_mejoras_docx()
│
├── integrations/               # Adaptadores de servicios externos
│   ├── __init__.py
│   ├── base.py                # IntegrationAdapter (interfaz)
│   ├── registry.py            # Registro singleton de adaptadores
│   ├── sync.py                # Cache sync
│   ├── jira/
│   │   ├── __init__.py
│   │   ├── integration.py     # JiraAdapter
│   │   └── oauth.py           # Flujo OAuth 2.0
│   ├── github/
│   │   ├── __init__.py
│   │   └── integration.py     # GitHubAdapter
│   └── gitlab/
│       ├── __init__.py
│       └── integration.py     # GitLabAdapter
│
├── models/                      # Pydantic models (no DB models)
│   ├── __init__.py
│   └── ai.py                  # AIModelInfo, ModelCatalogResponse
│
├── schemas/                     # Schemas para validación de request
│   ├── __init__.py
│   ├── user.py
│   ├── chat.py
│   ├── prd.py
│   ├── standup.py
│   ├── test_plan.py
│   └── settings.py
│
├── __init__.py
└── main.py                      # Entry point
```

---

## 🚀 Entry Point — `main.py`

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager

# Lifespan events (startup/shutdown)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    ensure_local_dirs()
    ensure_knowledge_dirs()
    ensure_ai_files()
    await init_db()
    yield
    # Shutdown (cleanup)

def create_app() -> FastAPI:
    app = FastAPI(
        title="QA Project MGMT",
        description="Local PM + QA command center with grounded AI.",
        version="0.2.0",
        lifespan=lifespan,
    )
    
    # CORS
    app.add_middleware(CORSMiddleware, ...)
    
    # Routers
    app.include_router(health_router)
    app.include_router(api_router)
    
    # SPA fallback (servir frontend desde /dist)
    app.mount("/assets", StaticFiles(...))
    
    return app

app = create_app()
```

**Ejecución en desarrollo:**
```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

---

## 🔐 Autenticación — `api/auth.py`

### Endpoints

#### `POST /api/auth/register`
Crear nueva cuenta.

**Request:**
```json
{
  "username": "john_doe",
  "password": "secure_password",
  "email": "john@example.com",
  "full_name": "John Doe",
  "role": "user"
}
```

**Response (201 Approved o Pending):**
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "status": "approved",
  "message": "Cuenta creada...",
  "user": {
    "id": "uuid",
    "username": "john_doe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "role": "user",
    "status": "approved"
  }
}
```

#### `POST /api/auth/login`
Iniciar sesión.

**Request:**
```json
{
  "username": "john_doe",
  "password": "secure_password"
}
```

**Response (200 OK):**
```json
{
  "token": "eyJ0eXAi...",
  "status": "approved",
  "message": "Inicio de sesión exitoso.",
  "user": {...}
}
```

#### `GET /api/auth/me`
Obtener perfil actual (requiere Bearer token).

**Headers:**
```
Authorization: Bearer eyJ0eXAi...
```

**Response (200 OK):**
```json
{
  "user": {
    "id": "uuid",
    "username": "john_doe",
    ...
  }
}
```

#### `PUT /api/auth/me`
Actualizar perfil (requiere Bearer token).

**Request:**
```json
{
  "full_name": "Jane Doe",
  "email": "jane@example.com",
  "password": "new_password"
}
```

---

## 🤖 Features AI — `api/features.py`

### Core Endpoints

#### `POST /api/features/standup`
Generar reporte diario desde Jira, GitHub, etc.

**Request:**
```json
{
  "query": "Generate standup from recent work",
  "sources": ["jira", "github"],
  "document_ids": [],
  "chat_context": "We were focusing on auth module"
}
```

**Response:**
```json
{
  "ok": true,
  "refused": false,
  "answer": "# Daily Standup\n## Completado\n- JIRA-123: Feature X...",
  "answer_clean": "# Daily Standup\n...",
  "artifacts": [],
  "citations": [
    {
      "index": 1,
      "id": "jira_PROJ-123",
      "source_type": "jira",
      "source_label": "PROJ/issues",
      "title": "PROJ-123: Feature X"
    }
  ],
  "meta": {
    "provider": "ollama",
    "model": "llama2",
    "log_id": "uuid",
    "artifact_count": 0
  }
}
```

#### `POST /api/features/ask`
Consulta grounded a la base de conocimiento.

**Request:**
```json
{
  "query": "¿Cuál es la arquitectura del módulo de auth?",
  "sources": ["knowledge"],
  "document_ids": ["doc_123"]
}
```

**Response:** Similar a standup.

#### `POST /api/features/prd-checker`
Validar especificación funcional.

**Request:**
```json
{
  "query": "Auditar este PRD",
  "sources": ["knowledge"],
  "document_ids": ["prd_doc_123"]
}
```

#### `POST /api/features/qa/{feature_key}`
Generar artefactos QA (regression, api_qa, visual_qa, etc).

**Keys disponibles:** `regression`, `api_qa`, `visual_qa`, `smart_test_data`, `release_readiness`

---

## 📚 Conocimiento — `api/knowledge.py`

#### `GET /api/knowledge/documents`
Listar documentos cargados.

**Response:**
```json
{
  "documents": [
    {
      "id": "uuid",
      "filename": "spec.pdf",
      "file_type": ".pdf",
      "file_size": 245000,
      "tags": ["spec", "v2.1"],
      "chunk_count": 12,
      "uploaded_at": "2026-09-29T10:30:00Z",
      "char_count": 45000
    }
  ]
}
```

#### `POST /api/knowledge/documents`
Subir un documento (multipart).

**Multipart form data:**
```
file: <binary>
tags: "spec,requirement,v2.1"
```

**Response:**
```json
{
  "document": {...}
}
```

#### `DELETE /api/knowledge/documents/{doc_id}`
Eliminar documento.

**Response:**
```json
{
  "ok": true
}
```

#### `POST /api/knowledge/retrieve`
Buscar chunks relevantes (RAG).

**Request:**
```json
{
  "query": "Architecture of auth module",
  "sources": ["knowledge"]
}
```

**Response:**
```json
{
  "chunks": [
    {
      "id": "chunk_1",
      "source_type": "knowledge",
      "title": "spec.pdf - Section 3",
      "content": "The auth module uses JWT tokens...",
      "relevance_score": 0.87
    }
  ]
}
```

---

## 🔌 Integraciones — `api/integrations.py`

#### `GET /api/integrations`
Listar estado de todas las integraciones.

**Response:**
```json
{
  "integrations": [
    {
      "id": "jira",
      "name": "Jira",
      "status": "connected",
      "auth_methods": ["oauth", "pat"],
      "capabilities": ["get_issues", "get_projects"],
      "account_label": "user@company.com",
      "oauth_configured": true
    },
    {
      "id": "github",
      "name": "GitHub",
      "status": "not_connected",
      "auth_methods": ["pat"],
      "capabilities": ["get_pull_requests", "get_commits", "get_repositories"]
    }
  ]
}
```

#### `POST /api/integrations/{id}/pat`
Conectar con Personal Access Token (GitHub, GitLab).

**Request:**
```json
{
  "token": "ghp_...",
  "selected_repos": ["repo1", "repo2"]
}
```

#### `POST /api/integrations/{id}/oauth/start`
Iniciar flujo OAuth 2.0 (Jira).

**Response:**
```json
{
  "authorization_url": "https://auth.atlassian.com/authorize?...",
  "state": "random_state",
  "auth_method": "oauth"
}
```

#### `GET /api/integrations/{id}/oauth/callback`
Receiver para redirect de OAuth (internal, llamado por navegador).

#### `POST /api/integrations/{id}/test`
Probar conexión.

**Response:**
```json
{
  "ok": true,
  "message": "Connected successfully",
  "details": {
    "user": "john_doe",
    "org": "company"
  }
}
```

#### `POST /api/integrations/{id}/sync`
Sincronizar caché de issues, PRs, etc.

**Response:**
```json
{
  "synced_at": "2026-09-29T11:00:00Z",
  "items_count": 42
}
```

---

## 🧠 AI Engine — `app/ai/`

### runner.py

**Función principal:**

```python
async def run_grounded_feature(
    *,
    feature: str,                      # "standup", "ask_product", etc.
    query: str,                        # User prompt
    sources: list[str] | None = None,
    document_ids: list[str] | None = None,
    chat_context: str | None = None,
    template_content: str | None = None,
) -> dict[str, Any]:
    """
    Orquesta el flujo completo:
    1. Obtiene prompt y rúbrica
    2. Ensambla contexto desde fuentes
    3. Valida que no esté vacío
    4. Resuelve proveedor AI
    5. Llama LLM
    6. Parsea múltiples artefactos
    7. Loguea auditoría
    """
```

**Respuesta:**

```python
{
    "ok": bool,
    "refused": bool,
    "reason": str | None,
    "answer": str,                  # Texto completo del LLM (con <artifact> tags)
    "answer_clean": str,            # Texto sin etiquetas XML
    "artifacts": list[dict],        # Artefactos parseados: [{title, extension, content}]
    "citations": list[dict],        # Chunks usados como fuente
    "context": dict,                # Bundle completo
    "meta": {
        "provider": str,            # "ollama", "openai", etc.
        "model": str,
        "log_id": str,
        "artifact_count": int
    }
}
```

### artifacts.py

**Parser de múltiples artefactos:**

```python
def extract_artifacts(raw_text: str) -> tuple[list[LLMArtifact], str]:
    """
    Extrae <artifact title="..." extension="...">...</artifact> del LLM output.
    Retorna (artifacts, clean_text).
    """
```

Soporta tags en progreso (durante streaming):
```xml
<artifact title="Analysis" extension="docx">
Content incompleto...
<!-- sin </artifact> si el stream no terminó -->
```

### templates.py

**Gestión de prompts y rúbricas:**

```python
def get_prompt(feature: str) -> dict:
    """Lee local/ai/prompts/{feature}.json"""

def get_rubric(feature: str) -> dict:
    """Lee local/ai/rubrics/{feature}.json"""

def save_prompt(feature: str, content: dict) -> dict:
    """Guarda prompt personalizado"""
```

**Estructura de prompt:**

```json
{
  "version": "1.0",
  "system": "You are a QA expert...",
  "user_template": "Analyze:\n{context}\n\nRubric:\n{rubric}\n\nQuery: {query}",
  "allowed_sources": ["knowledge", "jira", "github"]
}
```

### providers/

**Abstracción multi-proveedor:**

```python
class AIProvider(Protocol):
    async def complete(
        messages: list[AIMessage],
        max_tokens: int = 4096
    ) -> AICompletion:
        """Llamada única (no streaming)"""

    async def complete_stream(
        messages: list[AIMessage],
        max_tokens: int = 8192
    ) -> AsyncGenerator[str, None]:
        """Streaming token-by-token"""
```

**Resolución dinámica:**

```python
def resolve_provider() -> AIProvider:
    """Retorna proveedor según configuración actual"""
    config = get_ai_settings()
    provider_name = config.get("provider")
    model_name = config.get("model")
    
    if provider_name == "ollama":
        base_url = config.get("ollama_base_url")
        return LiteLLMProvider("ollama", model_name, base_url)
    elif provider_name == "openai":
        return LiteLLMProvider("openai", model_name)
    ...
```

---

## 💾 Capa de Datos — `app/db/`

### Repository Pattern

**Interfaz:**

```python
class IUserRepository(Protocol):
    async def get_by_id(id: str) -> dict | None
    async def get_by_username(username: str) -> dict | None
    async def create_user_with_password(...) -> dict
    async def update(id: str, updates: dict) -> dict
```

**Implementación SQLite:**

```python
class UserRepository(BaseRepository):
    async def get_by_id(id: str) -> dict | None:
        sql = "SELECT * FROM users WHERE id = ?"
        return await self._fetch_one(sql, (id,))
```

### Database Schema

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT,
    password_hash TEXT,
    password_salt TEXT,
    full_name TEXT,
    role TEXT DEFAULT 'user',
    status TEXT DEFAULT 'pending',
    created_at TEXT
);

CREATE TABLE chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    role TEXT,              -- 'user' | 'assistant'
    content TEXT,
    context_sources TEXT,   -- JSON array
    timestamp TEXT
);

CREATE TABLE standups (
    id TEXT PRIMARY KEY,
    title TEXT,
    content TEXT,           -- Markdown
    sources TEXT,           -- JSON array
    created_at TEXT
);

CREATE TABLE prd_reviews (
    id TEXT PRIMARY KEY,
    prd_title TEXT,
    content TEXT,
    created_at TEXT
);

CREATE TABLE test_plans (
    id TEXT PRIMARY KEY,
    title TEXT,
    content TEXT,
    created_at TEXT
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

---

## 🔐 Seguridad

### Hashing de Contraseñas

```python
def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """SHA-256 + Salt"""
    if not salt:
        salt = generate_salt()  # 32 hex chars
    combined = (salt + password).encode()
    pwd_hash = hashlib.sha256(combined).hexdigest()
    return pwd_hash, salt
```

### JWT Tokens

```python
def create_access_token(payload: dict, expires_in_seconds: int = 604800) -> str:
    """HMAC-SHA256 JWT, 7 días de expiración"""
    data = payload | {"exp": time.time() + expires_in_seconds}
    # Serializar a base64 + firmar

def decode_access_token(token: str) -> dict | None:
    """Verificar firma y expiración"""
```

### Cifrado de Credenciales

```python
def encrypt_secret(plain_text: str) -> str:
    """Fernet encryption, retorna string con prefijo 'enc::'"""
    cipher = Fernet(derive_key_from_secret())
    return "enc::" + cipher.encrypt(plain_text.encode()).decode()

def decrypt_secret(encrypted: str) -> str:
    """Desencripta si tiene prefijo, sino retorna como está"""
    if not encrypted.startswith("enc::"):
        return encrypted
    cipher = Fernet(derive_key_from_secret())
    return cipher.decrypt(encrypted[5:].encode()).decode()
```

---

## 📊 Logging & Auditoría

### AI Call Logging

```python
def log_ai_call(entry: dict) -> dict:
    """Escribe en local/ai/logs/{uuid}.json"""
    log_id = uuid4()
    log_path = LOCAL_DIR / "ai" / "logs" / f"{log_id}.json"
    
    log_data = {
        "id": log_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "feature": entry["feature"],
        "refused": entry["refused"],
        "provider": entry.get("provider"),
        "model": entry.get("model"),
        "output": entry.get("output"),
        "sources_used": entry.get("sources_used"),
        "chunk_ids": entry.get("chunk_ids"),
    }
    
    log_path.write_text(json.dumps(log_data, indent=2))
    return {"id": log_id}
```

---

## 🚀 Testing

```bash
cd backend
python -m pytest tests/unit/ -v --cov=app
```

---

¡Para más detalles sobre integración con el frontend, consulta [FRONTEND.md](./FRONTEND.md)!

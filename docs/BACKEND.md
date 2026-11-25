# Backend — Especificación Técnica

Guía completa de módulos Python, endpoints FastAPI, y patrones utilizados en el backend de FuncAssist.

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
├── context/                     # RAG Engine (PostgreSQL vectorial + full-text + trigramas)
│   ├── __init__.py
│   ├── models.py              # ContextChunk, ContextBundle
│   ├── knowledge.py           # Ingesta, chunking y almacenamiento en PostgreSQL
│   ├── knowledge_migration.py # Migración de datos legados a PostgreSQL, export y recovery
│   ├── retrieval.py           # Búsqueda híbrida (vectorial → full-text → trigramas)
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
│   ├── models.py              # Modelos ORM SQLAlchemy
│   ├── unit_of_work.py        # Unit of Work sync/async
│   ├── interfaces/            # Interfaces abstractas (I*)
│   │   ├── __init__.py
│   │   ├── user_repository.py
│   │   ├── organization_repository.py
│   │   ├── integration_repository.py
│   │   ├── settings_repository.py
│   │   └── secret_repository.py
│   └── repositories/          # Implementaciones concretas
│       ├── __init__.py
│       ├── base_repository.py
│       ├── user_repository.py
│       ├── mcp_server_repository.py
│       ├── history_repository.py
│       ├── template_repository.py
│       ├── transcription_repository.py
│       └── catalog_repository.py
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
      "auth_methods": ["oauth"],
      "capabilities": ["get_issues", "get_projects"],
      "account_label": "user@company.com",
      "oauth_configured": true
    },
    {
      "id": "github",
      "name": "GitHub",
      "status": "not_connected",
      "auth_methods": ["oauth"],
      "capabilities": ["get_pull_requests", "get_commits", "get_repositories"]
    }
  ]
}
```

> No existe un endpoint para conectar con Personal Access Token: los PAT no se admiten en ninguna integración.

#### `POST /api/integrations/{id}/oauth/start`
Iniciar flujo OAuth 2.0. Solo Jira (conexión personal de cada usuario). Para GitHub y GitLab se conectan con cuenta de servicio.

**Response:**
```json
{
  "authorization_url": "https://auth.atlassian.com/authorize?...",
  "state": "random_state",
  "auth_method": "oauth"
}
```

#### `GET /api/integrations/jira/callback`
Receptor del redirect de OAuth de Jira (lo llama el navegador). GitHub y GitLab ya no tienen callback.

#### `POST /api/integrations/{id}/service-account`
Solo administrador. Conecta la organización con un token de bot de solo lectura (GitLab). Responde 501 para Jira (cada usuario conecta la suya por OAuth). GitHub tiene su propia ruta, `POST /api/integrations/github/service-account` (ver abajo).

**Request:**
```json
{
  "token": "glpat-...",
  "base_url": "https://gitlab.example.com",
  "selected_repos": ["grupo/proyecto"]
}
```

Antes de guardar nada se comprueba que el token esté activo, no haya caducado y tenga solo los permisos `read_api` (obligatorio), `read_repository` y `read_user`; cualquier permiso de escritura o administración se rechaza con 400. `POST /api/integrations/{id}/test` repite la comprobación y devuelve alcances, caducidad y días restantes. Conectar, desconectar y elegir repositorios de GitHub y GitLab exigen rol de administrador.

#### `POST /api/integrations/github/service-account`
Solo administradores. Conecta la organización con una **GitHub App** instalada solo en los repositorios necesarios.

**Request:**
```json
{
  "app_id": "123456",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----
...
-----END RSA PRIVATE KEY-----",
  "installation_id": "7890123",
  "selected_repos": ["org/repo"]
}
```

`installation_id` es opcional si la App tiene una sola instalación. El backend firma un JWT con la clave privada, comprueba la instalación (activa, no suspendida) y rechaza la App si algún permiso no es de solo lectura (`write` o `admin`), si tiene permisos fuera de `metadata`, `contents`, `pull_requests` e `issues`, o si falta alguno de los obligatorios (`metadata`, `contents`, `pull_requests`). Nada se guarda si la validación falla. La clave privada se guarda cifrada y nunca se devuelve. Los tokens de instalación duran 1 hora, se piden bajo demanda, se renuevan solos y no se almacenan. `POST /api/integrations/github/test` genera un token nuevo y repite la comprobación de permisos. Errores: 400 (credencial o permisos rechazados), 502 (GitHub no responde).

#### Servidores MCP (administradores)

| Método | Ruta | Uso |
|---|---|---|
| `GET` | `/api/mcp-servers` | Lista los servidores con sus herramientas y aprobaciones |
| `POST` | `/api/mcp-servers` | Registra un servidor; nace sin ninguna herramienta aprobada |
| `PATCH` | `/api/mcp-servers/{id}` | Edita; cambiar el endpoint borra las aprobaciones |
| `DELETE` | `/api/mcp-servers/{id}` | Elimina el servidor |
| `PUT` | `/api/mcp-servers/{id}/tools` | Aprueba o revoca herramientas (`name`, `description`, `input_schema`, `read_only`, `approved`) |
| `POST` | `/api/mcp-servers/{id}/test` | Comprueba el endpoint |

`GET /api/me/mcp-servers` devuelve a los usuarios solo los servidores habilitados y sus herramientas aprobadas, sin endpoint ni credenciales. Cada aprobación queda fijada a un hash del nombre, la descripción y el esquema revisados: si el servidor los cambia, la herramienta deja de estar autorizada hasta que se apruebe de nuevo. Las herramientas que no son de solo lectura exigen la confirmación del usuario en cada ejecución.

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

**Resolución de proveedor y modelo:** `providers/factory.resolve_provider(provider_name, model_name, user_id, tier="main"|"fast")`. Los modelos por defecto se eligen del catálogo sincronizado; ver [AI_LAYER.md](./AI_LAYER.md) para el orden de resolución, las variables de entorno, las rutas del chat y el protocolo SSE v2. La transcripción (pipeline, contrato de progreso, API y variables) está en [TRANSCRIPTION_PROCESS.md](./TRANSCRIPTION_PROCESS.md).

---

## 💾 Capa de Datos — `app/db/`

### Repository Pattern

> La capa de datos utiliza SQLAlchemy 2 (async) sobre PostgreSQL con el driver psycopg 3.

Los repositorios reciben una sesión obligatoria por inyección y no crean sesiones ni ejecutan `commit()` internamente. Las APIs y servicios deben utilizar interfaces y dependencias de FastAPI. Las operaciones multi-entidad deben coordinarse mediante `AsyncUnitOfWork` o `SyncUnitOfWork` en `app/db/unit_of_work.py`.

```python
async with AsyncUnitOfWork() as uow:
    user = await uow.users.get_by_id(user_id)
    await uow.commit()  # commit explícito
```

El `UnitOfWork` comparte una única sesión entre repositorios, ejecuta rollback ante excepciones y cierra la sesión al salir del contexto. El commit es explícito; no se realiza automáticamente.

Los repositorios cubren usuarios, organizaciones, integraciones, secretos, configuraciones, historial, transcripciones, plantillas, catálogo de modelos y servidores MCP.

`app/core/integration_migration.py` es una excepción administrativa controlada para DDL, índices y advisory locks de PostgreSQL. No debe utilizarse como patrón para operaciones CRUD normales.

**Interfaz:**

```python
class IUserRepository(Protocol):
    async def get_by_id(id: str) -> dict | None
    async def get_by_username(username: str) -> dict | None
    async def create_user_with_password(...) -> dict
    async def update(id: str, updates: dict) -> dict
```

**Implementación (SQLAlchemy + PostgreSQL):**

```python
class UserRepository:
    async def get_by_id(self, user_id: str) -> dict | None:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        return user.to_dict() if user else None
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

`app/ai/logging.log_ai_call(entry)` añade una línea al archivo diario `USER_DATA_DIR/ai/logs/AAAA-MM-DD.jsonl` (escritura en un hilo, sin bloquear el event loop). `GET /api/ai/logs` y `GET /api/ai/logs/stats` leen esos archivos desde el final. Campos y métricas en [AI_LAYER.md](./AI_LAYER.md#logs-y-métricas).

---

## 🚀 Testing

```bash
cd backend
python -m pytest tests -v --cov=app
```

---

¡Para más detalles sobre integración con el frontend, consulta [FRONTEND.md](./FRONTEND.md)!

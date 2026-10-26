# Auditoría del Sistema y Línea Base — FuncAssist

**Fecha de auditoría:** 24 de Octubre de 2026  
**Rama de trabajo:** `feat/blueprint-modernization`  
**Stack tecnológico verificado:**
- Frontend: React 19.2.8, TypeScript 6.0.2, Vite 8.2.2, Tailwind CSS 4.3.3, Univer 1.0.2, React Router 7.18.2
- Backend: FastAPI (>=0.111.0), Pydantic 2.10+, Uvicorn, LiteLLM, Faster-Whisper, SQLite FTS5 + Rank-BM25, python-docx, openpyxl
- Entorno: Node v22.20.0, npm 10.9.3, Python 3.14.7 en Windows

---

## 1. Mapa del Sistema Actual

### 1.1 Frontend
- **Punto de entrada:** `frontend/src/main.tsx` → `frontend/src/App.tsx`.
- **Rutas principales:**
  - `/`: `DashboardPage`
  - `/funcional/mejoras`: `MejorasPage` → `AgenticDocumentWorkspace` con configuración `mejoras`.
  - `/funcional/inventario`: `InventarioPage` → `AgenticDocumentWorkspace` con configuración `inventario`.
  - `/funcional/levantamiento`: `LevantamientoPage` → `AgenticDocumentWorkspace`.
  - `/funcional/transcripciones`: `TranscripcionesPage` (estudio de transcripciones de audio/reuniones).
  - `/knowledge`: `KnowledgePage` (gestión de documentos de la base de conocimiento).
  - `/settings`: `SettingsPage` (configuración de LLMs, API Keys, Ollama, templates).
- **Workspace de Chat y Documento:**
  - Ubicación: `frontend/src/features/document/components/AgenticDocumentWorkspace.tsx`
  - Paneles:
    - Izquierda: `ChatHistorySidebar.tsx` (plegable, lista de sesiones).
    - Centro: Feed de mensajes + `AgenticThinkingBubble.tsx` + Input composer.
    - Derecha: `ArtifactsStudio.tsx` (plegable, editor Univer y listado de artefactos).
  - Estado y hooks:
    - `useChatPersistence`: almacena conversaciones y artefactos en `localStorage` del navegador.
    - `useAgenticGeneration`: orquesta el ciclo de envío de mensajes, estados de razonamiento y llamadas al endpoint SSE del backend.
    - `useArtifacts`: manipulación de versiones locales de artefactos y cambio de artefacto activo.
    - `useDocumentHistory`: undo/redo de contenido del documento activo.
  - API Client: `frontend/src/features/document/api/docAgentApi.ts` consume SSE mediante `fetch` y `ReadableStreamDefaultReader`.

### 1.2 Backend
- **Punto de entrada:** `backend/app/main.py` ejecutado vía Uvicorn en puerto `6728`.
- **Enrutador principal:** `backend/app/api/router.py` agrupa:
  - `document_agent`: endpoints `/api/doc-agent/agentic-prompt` y `/api/doc-agent/agentic-prompt-stream`.
  - `history`: endpoints `/api/chat/history/{session_id}` y `/api/history/*`.
  - `knowledge`: endpoints `/api/knowledge/documents` y carga de archivos.
  - `transcription`: endpoints `/api/transcription/*` y SSE stream de audio.
  - `ai_settings`, `ai_management`, `ai_templates`: configuración de LLM y plantillas.
- **Persistencia actual:**
  - Directorio base: `LOCALAPPDATA/funcassist` (resuelto en `backend/app/core/settings.py`).
  - Base de datos SQLite FTS5 para conocimiento (`knowledge.db` con tabla virtual `chunks_fts`).
  - JSON Files para historial de chat y settings (`USER_DATA_DIR/history/chat_{session_id}.json`).
  - Credenciales cifradas con Fernet en `connections/`.
- **Motor de IA y RAG:**
  - `backend/app/ai/runner.py`: función `run_grounded_feature` y `run_grounded_feature_stream`.
  - `backend/app/context/service.py`: `assemble_context` consulta SQLite FTS5 y rank-bm25, integrando fuentes externas (Jira, GitHub).
  - Rúbricas y prompts: `backend/app/ai/templates.py` almacena valores predeterminados de sistema y usuario.
- **Generadores Documentales:**
  - DOCX: `backend/app/features/mejoras/docx_builder.py` (`python-docx`).
  - XLSX: `backend/app/features/inventario/xlsx_builder.py` (`openpyxl`).

---

## 2. Hallazgos y Deuda Técnica Identificada

1. **Desacoplamiento de eventos vs. razonamiento:**
   - En el frontend (`useAgenticGeneration.ts`), los pasos de pensamiento (`ThinkingStep`) se simulan mediante `setTimeout(..., 400)` estáticos en el cliente, en lugar de recibir eventos SSE operacionales del backend.
   - El endpoint actual `/api/doc-agent/agentic-prompt-stream` sólo emite chunks de texto `{ "type": "token", "text": "..." }` y una respuesta final `{ "type": "full", ... }`.
2. **Generación basada en texto plano vs. esquemas estructurados:**
   - El backend invoca al modelo para generar Markdown en texto libre y luego utiliza expresiones regulares (`parseMultipleArtifacts` en cliente o `artifacts.py` en backend) para extraer bloques.
   - No existe validación determinista previa mediante Pydantic schemas para los tipos clave (`functional_improvement`, `functional_inventory`).
3. **Persistencia y memoria dual no sincronizada:**
   - El frontend mantiene historial en `localStorage` (`useChatPersistence`), mientras el backend expone repositorios JSON (`JsonChatRepository`) que actualmente no sincronizan el contexto completo de decisiones y memoria condensada del proyecto.
4. **Plantillas y marcadores:**
   - La generación de DOCX/XLSX está codificada en builders imperativos (`docx_builder.py`, `xlsx_builder.py`) sin un motor declarativo de marcadores estructurados (`{{artifact.field}}`, `{{#each}}`).
5. **Entrada de voz:**
   - Existe un subsistema completo de transcripción para archivos y streaming de reuniones (`transcription/`), pero falta un control nativo directo en el composer de chat que permita dictar y revisar el texto antes de enviarlo.

---

## 3. Estado de la Línea Base de Pruebas

- **Frontend Oxlint:** 0 errores, 56 advertencias (reglas de React compiler / exhaustividad de dependencias preexistentes).
- **Frontend Typecheck (`tsc -b`):** Resuelto mediante declaración de tipos ambientales para `lucide-react` en `frontend/src/types/lucide-react.d.ts`.
- **Backend Tests (`pytest backend/tests`):** Requiere entorno virtual activo (`.venv`) y variable `PYTHONPATH=backend` para resolver el paquete raíz `app`.

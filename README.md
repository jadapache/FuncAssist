# QA Project MGMT

> Centro de comando local con IA para Product Managers e Ingenieros de QA. Integra búsqueda RAG contextual, almacenamiento local cifrado, integraciones desacopladas (Jira, GitHub, GitLab), generación de documentos con editor en tiempo real y suite completa de herramientas QA/PM.

**Estado**: 🚀 En desarrollo activo. V0.2.0+  
**Documentación completa**: Consulta [`docs/`](./docs/) para guías detalladas de arquitectura, backend, frontend y despliegue.

---

## 🚀 Inicio Rápido (< 5 minutos)

### Requisitos previos
- **Node.js**: v18+ (v20+ recomendado)
- **Python**: 3.11+ (probado en Python 3.11 – 3.14)
- **Git**: v2+

### 1. Clonar y Configurar el Entorno
```bash
git clone https://github.com/tu-org/qa-mgmt.git
cd qa-mgmt
cp .env.example .env
```

*(Opcional: Configura las claves del proveedor de IA o credenciales de integración en `.env`, o bien configúralas desde la UI despues de iniciar)*

### 2. Instalación de Dependencias

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend (en otra terminal desde raíz)
cd frontend
npm install
```

### 3. Ejecución en Desarrollo

```bash
# Terminal 1 - Backend (FastAPI en http://127.0.0.1:8000)
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 - Frontend (Vite en http://localhost:5173)
cd frontend
npm run dev
```

### 4. Acceso

- **Aplicación Web**: [http://localhost:5173](http://localhost:5173)
- **Swagger API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health Check**: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

> **¿Primera vez?** Ver [Inicio Rápido Completo](./docs/QUICKSTART.md) para guía paso a paso con screenshots y troubleshooting.

---

## 📚 Documentación

La documentación técnica completa está disponible en **[`docs/`](./docs/)**:

- **[README (docs/)](./docs/README.md)** — Índice y descripción general
- **[QUICKSTART](./docs/QUICKSTART.md)** — Guía paso a paso (5 min)
- **[ARCHITECTURE](./docs/ARCHITECTURE.md)** — Diseño del sistema, flujos, principios
- **[BACKEND](./docs/BACKEND.md)** — Módulos Python, endpoints FastAPI, AI engine
- **[FRONTEND](./docs/FRONTEND.md)** — Componentes React, hooks, gestión de estado
- **[CI/CD & DESKTOP RELEASES](./docs/CICD_RELEASE_GUIDE.md)** — Pipeline automatizado de GitHub Actions y releases Tauri (.msi / .exe)

---

## 🛠 Stack Tecnológico

| Capa | Tecnología | Versión |
|------|-----------|---------|
| **Frontend** | React, TypeScript, Vite, Tailwind CSS v4, React Router | 19 / 6 / 8 / 4 / 7 |
| **Backend** | Python, FastAPI, Pydantic | 3.11+ / 0.111+ / 2.8+ |
| **IA & RAG** | LiteLLM, BM25, pypdf, python-docx | 1.35+ / 0.2.2 / 5.4 / 1.1 |
| **Almacenamiento** | Local JSON (`app.json`), Fernet encryption, local history | JSON-only |
| **Seguridad & Acceso** | Rol de usuario local (`admin`, `pm`, `funcional`, `dev`, `qa`), cryptography, keyring | 44+ / 25.6+ |

---

## 📂 Estructura del Proyecto

```
QA_MGMT/
├── docs/                     # 📍 Documentación técnica completa (nuevo)
│   ├── README.md            # Índice de documentación
│   ├── QUICKSTART.md        # Guía de inicio rápido
│   ├── ARCHITECTURE.md      # Diseño y flujos
│   ├── BACKEND.md           # Especificación backend
│   └── FRONTEND.md   # Especificación frontend
│
├── backend/                 # FastAPI + AI Engine + RAG
│   ├── app/
│   │   ├── ai/             # Motor LLM multiproveedor, prompts, templates, logging
│   │   ├── api/            # Routers FastAPI (auth, features, knowledge, doc-agent, integrations)
│   │   ├── context/        # RAG: ingesta, BM25, ensamblaje de contexto
│   │   ├── core/           # Settings, security, secrets (Fernet), storage
│   │   ├── db/             # Repository pattern, interfaces, SQLite
│   │   ├── features/       # Servicios (standup, mejoras funcionales)
│   │   ├── integrations/   # Adaptadores (Jira OAuth/PAT, GitHub PAT, GitLab PAT)
│   │   ├── models/         # Pydantic models (AI catalog)
│   │   ├── schemas/        # Schemas de validación (user, chat, prd, test_plan)
│   │   └── main.py         # Entry point
│   ├── requirements.txt    # Dependencias Python (openpyxl, litellm, etc)
│   └── tests/              # Tests unitarios
│
├── frontend/               # React 19 SPA (Vite + Tailwind)
│   ├── src/
│   │   ├── pages/         # Dashboard, Standup, PRD, QA, Knowledge, Settings
│   │   ├── components/    # AppLayout, Workspace, DocumentAgent, Integrations
│   │   ├── hooks/         # useChatPersistence, useArtifacts, useDocumentHistory
│   │   ├── api/           # Cliente HTTP tipado (client.ts)
│   │   ├── context/       # AuthContext, ToastContext
│   │   ├── document_agent/ # DocumentAgent orchestrator + Univer adapter
│   │   ├── utils/         # artifactSplitter, helpers
│   │   └── App.tsx        # Router principal
│   ├── package.json       # Dependencies & scripts
│   └── vite.config.ts
│
├── local/                 # Almacenamiento en tiempo de ejecución
│   ├── connections/       # Credenciales encriptadas (.enc)
│   ├── ai/               # Prompts, rúbricas, logs, catálogo de modelos
│   ├── knowledge/        # Documentos, chunks indexados
│   └── database.db       # SQLite
│
├── Dockerfile            # Contenedor multietapa para producción
├── .env.example          # Template de variables de entorno
├── .dockerignore
├── .gitignore
├── render.yaml           # Config de despliegue Render
└── README.md             # Este archivo
```

---

## ✨ Funcionalidades Principales

### 🎯 Herramientas PM

- **Generador de Standup Diario**: Consolida tareas abiertas, trabajo reciente y bloqueos desde Jira y GitHub para generar reportes estructurados.
- **Revisor de PRD**: Audita documentos de especificaciones analizando claridad, criterios de aceptación, vacíos y riesgos con rúbricas personalizables.
- **Análisis de Impacto de Cambios**: Evalúa los efectos de cambios propuestos sobre arquitectura, código y suites de prueba.

### 🧪 Herramientas QA

- **Suite QA Completa**: Generadores para:
  - Matrices de pruebas de Regresión
  - Listas de verificación QA de APIs
  - QA Visual
  - Datos de prueba inteligentes
  - Evaluación de Estado de Lanzamiento

- **Panel QA Integrado**: Entorno especializado que cubre todos los tipos de pruebas en un flujo unificado.

### 📚 Base de Conocimiento RAG Local

- **Ingesta Multi-formato**: Soporta PDF, DOCX, Markdown, TXT
- **Búsqueda BM25**: Ranking rápido e interpretable sin dependencias de LLMs
- **Chat Grounded**: Consultas conversacionales fundamentadas en documentación cargada
- **Zero-shot Offline**: Funciona completamente sin conexión a internet (con Ollama local)

### 🔌 Integraciones Desacopladas

- **Jira**: OAuth 2.0 (Atlassian 3LO) + Personal Access Token (PAT)
- **GitHub**: PAT con selección de repositorios
- **GitLab**: PAT con inspección de proyectos
- Sincronización automática de caché sin bloqueos

### 🤖 Motor de IA Multiproveedor

- **Ollama** (local, privado) — Modelos: llama2, mistral, qwen, etc.
- **OpenAI** (GPT-4, GPT-3.5)
- **Anthropic** (Claude)
- Prompts editables desde UI
- Rúbricas de evaluación personalizables
- Auditoría completa de llamadas AI

### 📄 Generador de Documentos Funcionales (Agentic RAG)

- **Edición en Tiempo Real**: Editor visual (Univer.js) con soporte para documentos y hojas de cálculo
- **Múltiples Artefactos**: Genera documentos independientes en una sola solicitud
- **Operaciones Canónicas**: Inserta/reemplaza/mueve contenido de forma estructurada
- **Export Nativo**: Descarga como .docx o .xlsx sin dependencias web
- **Undo/Redo**: Historial ilimitado de cambios
- **Autosave**: Guardado automático cada 1.5 segundos

---

## 🔐 Seguridad y Almacenamiento Local

- **Sin base de datos remota**: Almacenamiento 100% local (SQLite, JSON, Fernet)
- **Secretos Cifrados**: Tokens y PATs encriptados con Fernet usando keyring del sistema
- **Jerarquía de Claves**: `keyring` → hardware fingerprint → `PMQA_SECRET_KEY`
- **Desconexión Limpia**: Eliminación permanente de archivos `.enc` al desconectar servicios
- **Validación Pydantic**: Schemas estrictos en todos los endpoints

---

## 📦 Despliegue

### Desarrollo Local
```bash
# Backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend
npm run dev
```

### Producción (Docker)
```bash
docker build -t qa-mgmt:latest .
docker run -p 8000:8000 -e VITE_API_BASE=http://localhost:8000 qa-mgmt:latest
```
---
# QA Project MGMT — Documentación del Sistema

Bienvenido a la documentación técnica de **QA Project MGMT**, un sistema local de gestión de QA y PM potenciado con IA generativa, integración empresarial y RAG grounded.

## 📚 Índice

- **[Inicio Rápido](./QUICKSTART.md)** — Instalación, compilación y ejecución en 5 minutos.
- **[Arquitectura](./ARCHITECTURE.md)** — Diagrama de capas, flujos de datos y principios de diseño.
- **[Backend](./BACKEND.md)** — Módulos Python, endpoints FastAPI, AI engine, integración con servicios externos.
- **[Frontend](./FRONTEND.md)** — Componentes React, hooks personalizados, gestión de estado, interfaz de usuario.
- **[API Reference](./API_REFERENCE.md)** — Especificación completa de endpoints REST.
- **[CI/CD & Desktop Releases](./CICD_RELEASE_GUIDE.md)** — Pipeline de GitHub Actions, compilación Windows MSI/EXE y auto-actualizaciones.
- **[Database Schema](./DATABASE.md)** — Modelos de datos, tablas SQLite, relaciones.
- **[Deployment](./DEPLOYMENT.md)** — Docker, Render.com, configuración de producción.
- **[Contributing](./CONTRIBUTING.md)** — Guía para contribuidores: convenciones de código, branching, testing.
- **[Troubleshooting](./TROUBLESHOOTING.md)** — Solución de problemas comunes y FAQ.

---

## 🎯 Descripción General

QA Project MGMT es una solución integrada para equipos de QA y Product Management que permite:

### Funcionalidades Principales

1. **Standup Automático** — Genera reportes diarios desde commits de GitHub, PRs en revisión e issues de Jira.
2. **Auditoría de PRD** — Valida especificaciones funcionales contra rúbricas de calidad y propone mejoras.
3. **Análisis de Impacto** — Evalúa el impacto de cambios sobre la arquitectura y estrategia de pruebas.
4. **QA Features** — Suite de generadores: regression test matrices, casos de API QA, datos de prueba inteligentes.
5. **Generador de Mejoras Funcionales** — Documento agentic de especificaciones funcionales con edición en tiempo real.
6. **Base de Conocimiento Local** — Ingesta de PDFs, DOCXs, MDs; RAG con BM25 para consultas grounded.
7. **Integración Multiproveedor** — Jira (OAuth + PAT), GitHub (PAT), GitLab (Token), con sincronización de caché.
8. **AI Multiproveedor** — Ollama local, OpenAI, Anthropic Claude, con fallback dinámico.

---

## 🏗️ Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| **Frontend** | React 19, TypeScript 6, Vite 8, Tailwind CSS 4, React Router 7 |
| **Backend** | Python 3.11+, FastAPI, Pydantic, SQLite con aiosqlite |
| **AI** | LiteLLM (multi-provider), Ollama (local), OpenAI, Anthropic |
| **RAG** | BM25 (rank-bm25), ingesta de documentos (pypdf, python-docx) |
| **Desktop** | Tauri (integración Rust opcional) |
| **Deployment** | Docker, Render.com, HTTPS ready |

---

## 📋 Requisitos Previos

- **Node.js** ≥ 18.x
- **Python** ≥ 3.11
- **pip** o **uv** (package manager)
- **Git**
- Navegador moderno (Chrome, Firefox, Safari, Edge)

Para desarrollo local con Ollama:
- **Docker Desktop** o **Ollama CLI** instalado

---

## 🚀 Estructura del Repositorio

```
QA_MGMT/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── ai/                # Motor LLM (runner, templates, providers, catalog, logging)
│   │   ├── api/               # Routers FastAPI (auth, features, integrations, doc_agent, etc.)
│   │   ├── context/           # RAG engine (knowledge, retrieval, service)
│   │   ├── core/              # Núcleo (settings, storage, security, secrets)
│   │   ├── db/                # Capa de datos (repositories, interfaces, database)
│   │   ├── features/          # Servicios (standup, mejoras)
│   │   ├── integrations/      # Adaptadores (github, gitlab, jira, registry, sync)
│   │   ├── models/            # Pydantic models (AI, catalog)
│   │   ├── schemas/           # Schemas para DB (chat, prd, standup, test_plan, user)
│   │   └── main.py            # Entry point
│   ├── requirements.txt        # Dependencias Python
│   └── tests/                 # Tests unitarios
├── frontend/                  # React SPA
│   ├── src/
│   │   ├── api/               # Cliente HTTP (client.ts)
│   │   ├── components/        # Componentes React
│   │   ├── pages/             # Rutas / páginas
│   │   ├── hooks/             # Hooks personalizados
│   │   ├── context/           # Context API (auth, toast)
│   │   ├── types.ts           # Tipos TypeScript
│   │   ├── utils/             # Utilidades
│   │   ├── constants/         # Constantes (features, app config)
│   │   ├── document_agent/    # DocumentAgent para edición de documentos
│   │   └── main.tsx           # Entry point
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── docs/                      # 📍 Documentación técnica (este directorio)
├── local/                     # Datos en tiempo de ejecución (NO se commitea)
│   ├── connections/           # Credenciales encriptadas
│   ├── ai/                    # Prompts, rúbricas, modelos, logs
│   └── knowledge/             # Índices de documentos, chunks
├── .env.example               # Template de variables de entorno
├── Dockerfile                 # Imagen Docker para producción
├── render.yaml                # Configuración de despliegue Render
└── README.md                  # Raíz del proyecto
```

---

## 🔐 Seguridad

- **Credenciales**: Encriptadas con Fernet (cryptography) usando clave derivada de entorno o keyring del sistema.
- **Tokens JWT**: Bearer tokens con firma HMAC-SHA256 y expiración de 7 días.
- **CORS**: Configurable por entorno, restringido a orígenes conocidos.
- **Validación**: Pydantic schemas con validación estricta de entrada.

---

## 🧪 Testing

```bash
# Backend
cd backend
python -m pytest tests/ -v

# Frontend
cd frontend
npm run build  # TypeScript type check incluido
```

---

## 📦 Compilación y Despliegue

```bash
# Desarrollo local
# Backend
cd backend && python -m uvicorn app.main:app --reload

# Frontend (en otra terminal)
cd frontend && npm run dev

# Producción con Docker
docker build -t qa-mgmt:latest .
docker run -e VITE_API_BASE=http://localhost:8000 -p 8000:8000 qa-mgmt:latest

# Despliegue en Render.com (ver DEPLOYMENT.md)
```

---

## 🤝 Contribuciones

Por favor, consulta [CONTRIBUTING.md](./CONTRIBUTING.md) para:
- Convenciones de código
- Flujo de branching
- Proceso de PR
- Estándares de testing

---

## 📖 Licencia

Este proyecto es interno. Contacta al equipo para detalles de licencia.

---

## 🆘 Soporte

- **Documentación técnica**: Ver [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)
- **Reporte de bugs**: Abre un issue en GitHub con detalles, pasos de reproducción y logs.
- **Feature requests**: Discute en el equipo antes de abrir un issue.

---

**Última actualización**: Septiembre 2026

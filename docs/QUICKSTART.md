# Inicio Rápido — QA Project MGMT

Instala, compila y ejecuta QA Project MGMT en tu máquina local en **menos de 5 minutos**.

---

## 📋 Requisitos Previos

✅ **Node.js** ≥ 18.x  
✅ **Python** ≥ 3.11  
✅ **Git**  
✅ Navegador moderno

Verifica las versiones:

```bash
node --version       # v18.0.0 o superior
python --version     # Python 3.11.x o superior
git --version        # Git 2.x
```

---

## 🚀 Instalación (5 minutos)

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-org/qa-mgmt.git
cd qa-mgmt
```

### 2. Configurar variables de entorno

Copia el template y edita si es necesario:

```bash
cp .env.example .env
```

Contenido por defecto en `.env`:

```env
# Backend
FASTAPI_ENV=development
PMQA_SECRET_KEY=         # (opcional) dejar vacío para usar keyring del sistema

# Frontend
VITE_API_BASE=http://127.0.0.1:8000

# Integrations (opcional por ahora)
JIRA_CLIENT_ID=
JIRA_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# AI Provider (deja vacío por ahora, configurable desde UI)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GROQ_API_KEY=
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

> No necesitas credenciales aún. Puedes configurarlas desde la interfaz más adelante.

### 3. Instalar dependencias del Backend

```bash
cd backend
python -m pip install -U pip
pip install -r requirements.txt
```

> Si prefieres `uv` (más rápido):
> ```bash
> pip install uv
> uv pip install -r requirements.txt
> ```

### 4. Instalar dependencias del Frontend

```bash
cd ../frontend
npm install
```

---

## ⚙️ Ejecutar en Desarrollo

### Terminal 1: Backend FastAPI

```bash
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Deberías ver:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

✅ Backend listo en `http://127.0.0.1:8000`

### Terminal 2: Frontend Vite

```bash
cd frontend
npm run dev
```

Deberías ver:

```
  VITE v8.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  press h to show help
```

✅ Frontend listo en `http://localhost:5173`

---

## 🌐 Acceder a la Aplicación

Abre tu navegador en:

```
http://localhost:5173
```

### Primera vez

1. **Configuración Inicial**: Al abrir la app por primera vez, verás un modal de bienvenida.
   - Ingresa tu nombre (ej: "María González")
   - Selecciona tu rol (`Director de Proyecto`, `Analista Funcional`, `Tester`)
   - Haz clic en "Comenzar"

2. **Dashboard**: Accederás directamente al dashboard con las secciones visibles filtradas según tu rol.

3. **Cambio de Nombre**: Puedes cambiar tu nombre cualquier momento desde Perfil.

---

## 🧪 Verificación Rápida

Prueba cada módulo sin configuración previa:

### 1. Health Check

```bash
curl http://127.0.0.1:8000/api/health
```

Respuesta esperada:

```json
{"status": "ok", "app": "QA Project MGMT"}
```

### 2. Generar Standup (sin contexto)

```bash
curl -X POST http://127.0.0.1:8000/api/features/standup \
  -H "Content-Type: application/json" \
  -d '{"query": "Resumen de hoy"}'
```

Resultado: Debería rechazarse sin fuentes conectadas (respuesta: `refused=true`).

### 3. Cargar Documento de Prueba

Desde la UI:
1. Navega a **Conocimiento** → **Subir Documentos**
2. Sube un PDF, DOCX o TXT de prueba
3. Etiqueta como `general` o similar

### 4. Consultar la Base de Conocimiento

```bash
curl -X POST http://127.0.0.1:8000/api/knowledge/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "tu pregunta aquí", "sources": ["knowledge"]}'
```

---

## 🔌 Configurar Integraciones (Opcional)

### Jira

1. Navega a **Configuración** → **Integraciones** → **Jira**
2. Elige **OAuth** o **PAT**:
   - **OAuth**: Click en "Conectar" (abre Atlassian login)
   - **PAT**: Genera token en Jira Cloud Settings → Security → API Tokens, pega en el formulario
3. Click en "Conectar" y luego "Probar conexión"

### GitHub

1. **Configuración** → **Integraciones** → **GitHub**
2. Genera PAT en GitHub → Settings → Developer Settings → Personal Access Tokens → Tokens (classic)
3. Scopes mínimos: `repo`, `read:user`
4. Pega en el formulario y "Conectar"

### Ollama (Local, Recomendado para Desarrollo)

1. Instala [Ollama](https://ollama.ai) o ejecuta en Docker:
   ```bash
   docker run -d -p 11434:11434 ollama/ollama
   ```

2. Descarga un modelo (ej: Llama 2):
   ```bash
   ollama pull llama2
   ```

3. **Configuración** → **AI Provider** → Selecciona **Ollama**
4. Base URL: `http://127.0.0.1:11434` (default)
5. Click en "Probar conexión" → selecciona `llama2` del dropdown
6. ¡Listo!

---

## 📁 Estructura de Directorios Generados

Cuando ejecutes por primera vez, se crea:

```
local/
├── ai/
│   ├── prompts/              # Plantillas de prompts
│   ├── rubrics/              # Rúbricas de evaluación
│   ├── models_catalog.json   # Catálogo de modelos disponibles
│   └── logs/                 # Auditoría de llamadas AI (JSON)
├── connections/              # Credenciales encriptadas por servicio
├── knowledge/
│   ├── documents.json        # Índice de documentos cargados
│   ├── chunks.json           # Chunks de texto indexados con BM25
│   └── uploads/              # Archivos originales cargados
└── database.db               # SQLite con usuarios, chats, standups
```

No commitees `local/` — está en `.gitignore`.

---

## 🛠️ Desarrollo Local

### Hot Reload

- **Backend**: Uvicorn automáticamente recarga al cambiar archivos Python (flag `--reload`)
- **Frontend**: Vite hot-reloads CSS y componentes React al guardar

### Linting & Type Checking

```bash
# Backend
cd backend
python -m pytest tests/ -v     # Tests

# Frontend
cd frontend
npm run lint                   # ESLint con oxlint
npm run build                  # TypeScript type check
```

### Ver logs del Backend

El backend loguea en `stderr` en modo desarrollo. Para más detalle:

```bash
LOGLEVEL=DEBUG python -m uvicorn app.main:app --reload
```

---

## 🐛 Troubleshooting Rápido

### "Port 8000 already in use"

```bash
# Linux/Mac
lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Windows PowerShell
Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process -Force
```

Luego re-inicia el backend.

### "ModuleNotFoundError: No module named 'app'"

Asegúrate de ejecutar desde `backend/`:

```bash
cd backend
python -m uvicorn app.main:app --reload
```

### "Cannot find module '@univerjs/core'"

```bash
cd frontend
npm install
```

### "localhost:5173 en blanco / error CORS"

1. Verifica que backend esté corriendo: `curl http://127.0.0.1:8000/api/health`
2. Revisa que VITE_API_BASE en `.env` sea correcto
3. Abre DevTools (F12) → Console → busca errores de fetch

### "Error al cargar documento"

- Verifica formato: `.pdf`, `.docx`, `.txt`, `.md` soportados
- Tamaño máximo: ~50 MB (configurable)
- Revisa backend logs para detalles

---

## 📞 Próximos Pasos

1. **Lee [ARCHITECTURE.md](./ARCHITECTURE.md)** para entender el diseño del sistema
2. **Explora [BACKEND.md](./BACKEND.md)** para módulos Python
3. **Consulta [API_REFERENCE.md](./API_REFERENCE.md)** para endpoints
4. **Ve [CONTRIBUTING.md](./CONTRIBUTING.md)** si quieres contribuir

---

## ✨ Comandos Útiles

```bash
# Reset total (borra base de datos y archivos locales)
rm -rf backend/database.db local/

# Rebuild frontend
cd frontend && npm run build

# Ver logs del DB (SQLite)
sqlite3 backend/database.db ".schema"

# Exportar prompt actual
curl http://127.0.0.1:8000/api/ai/prompts/standup | jq .

# Listar documentos cargados
curl http://127.0.0.1:8000/api/knowledge/documents | jq .
```

---

¡Listo! 🎉 Tu instancia local de QA Project MGMT está corriendo.

**¿Preguntas?** Consulta [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) o abre un issue.

# Frontend — Especificación Técnica

Guía completa de componentes React, hooks personalizados, gestión de estado y arquitectura del frontend de FuncAssist.

---

## 📂 Estructura de Directorios

```
frontend/src/
├── pages/                       # Rutas / Páginas
│   ├── DashboardPage.tsx       # Home / Status
│   ├── LoginPage.tsx           # Auth
│   ├── pm/
│   │   ├── StandupPage.tsx    # Generador de Standup
│   │   └── PmFeaturePage.tsx  # Features PM genéricas
│   ├── funcional/
│   │   ├── MejorasPage.tsx    # Generador de Mejoras Funcionales
│   │   ├── LevantamientoPage.tsx
│   │   └── FuncionalFeaturePage.tsx
│   ├── qa/
│   │   └── QaFeaturePage.tsx  # Features QA
│   ├── conocimiento/
│   │   ├── KnowledgePage.tsx  # Upload documentos, manager
│   │   └── AskProductPage.tsx # Chat RAG
│   └── configuraciones/
│       ├── SettingsPage.tsx   # AI provider, API keys
│       ├── ProfilePage.tsx    # Perfil de usuario
│       └── IntegrationsPage.tsx
│
├── components/                  # Componentes React reutilizables
│   ├── AppLayout.tsx           # Layout principal (sidebar, topbar)
│   ├── FeatureWorkspace.tsx    # Componente base para features
│   ├── auth/
│   │   ├── ProtectedRoute.tsx
│   │   └── LoginForm.tsx
│   ├── common/
│   │   ├── Toast.tsx           # Toast notifications
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   └── Badge.tsx
│   ├── document_workspace/
│   │   ├── DocumentChatBar.tsx
│   │   ├── UniverContainer.tsx # Univer editor wrapper
│   │   ├── DocumentInspectorModal.tsx
│   │   └── UniverPoCView.tsx
│   ├── workspace/
│   │   ├── AgenticDocumentWorkspace.tsx  # 📍 Centro de la app (Mejoras)
│   │   ├── ArtifactsStudio.tsx           # Panel de artefactos
│   │   ├── ChatHistorySidebar.tsx
│   │   ├── AgenticThinkingBubble.tsx
│   │   └── DocumentPanel.tsx
│   ├── integrations/
│   │   ├── JiraConnectCard.tsx
│   │   ├── GitHubConnectCard.tsx
│   │   └── GitLabConnectCard.tsx
│   ├── settings/
│   │   ├── AIProviderSelector.tsx
│   │   ├── ApiKeyInput.tsx
│   │   └── OllamaSettings.tsx
│   └── ui/
│       └── Icons.tsx (re-exporta lucide-react)
│
├── hooks/                       # Hooks personalizados
│   ├── useChatPersistence.ts   # Gestión de conversaciones (localStorage)
│   ├── useArtifacts.ts         # Gestión de múltiples artefactos
│   ├── useDocumentHistory.ts   # Undo/redo para documentos
│   ├── useAgenticGeneration.ts # Orquestación de RAG + LLM
│   ├── useCorporateTemplate.ts # Carga de template corporativa
│   └── useDocumentHistory.ts   # Historial de cambios
│
├── context/                     # Context API
│   ├── AuthContext.tsx         # user, token, login/logout
│   └── ToastContext.tsx        # Toast notifications
│
├── document_agent/             # DocumentAgent (editor canónico)
│   ├── core/
│   │   ├── DocumentAgent.ts    # Orquestador (Inspect → Validate → Execute → Verify)
│   │   └── types.ts            # Tipos canónicos (Artifact, Operation, State)
│   └── adapters/
│       └── UniverAdapter.ts    # Adapter para Univer.js
│
├── api/                         # Cliente HTTP
│   └── client.ts               # Fetch wrapper + tipos (GroundedResult, etc)
│
├── types/                       # Tipos TypeScript compartidos
│   └── artifacts.ts            # Artifact, ArtifactExtension
│
├── constants/                   # Configuración constante
│   ├── app.ts                  # General (AUTH_TOKEN_KEY, etc)
│   ├── funcionalFeatures.ts    # Configuración de Mejoras, etc
│   ├── pmFeatures.ts
│   └── qaFeatures.ts
│
├── utils/                       # Utilidades
│   ├── artifactSplitter.ts    # Parser de múltiples artefactos
│   ├── chatStorage.ts          # localStorage helper
│   └── helpers.ts              # Funciones varias
│
├── assets/                      # Recursos estáticos
│   └── ...
│
├── App.tsx                      # Router principal
├── main.tsx                     # Entry point
├── index.css                    # Tailwind + custom theme
├── types.ts                     # Tipos globales (IntegrationInfo, etc)
└── vite-env.d.ts              # Type declarations
```

---

## 🎨 Sistema de Diseño

### Tailwind CSS v4 + Custom Theme

**Color Palette:**

```css
/* Primary */
--primary: #002777;        /* Navy azul oscuro */
--primary-light: #003399;  /* Navy más claro */

/* Neutrals */
--bg-dark: #0b0f19;        /* Fondo oscuro */
--bg-panel: #1e293b;       /* Panels slate */
--bg-hover: #2d3748;       /* Hover state */

/* Accents */
--emerald: #10b981;        /* Verde éxito */
--cyan: #06b6d4;           /* Cyan info */
--red: #ef4444;            /* Red error */
--amber: #f59e0b;          /* Amber warning */

/* Typography */
--text-primary: #f1f5f9;
--text-secondary: #cbd5e1;
--text-muted: #94a3b8;
```

**Componentes Base:**

- Buttons: `btn-primary`, `btn-secondary`, `btn-ghost`
- Cards: `card`, `card-hover`
- Inputs: `input`, `textarea`, `select`
- Badges: `badge-primary`, `badge-success`, `badge-warning`

### Iconografía

Usamos `lucide-react` (~100 íconos). Importar así:

```typescript
import { FileText, Download, ChevronLeft, Sparkles } from 'lucide-react'
```

---

## 🔄 Hooks Personalizados

### useChatPersistence

Gestiona conversaciones y persistence en localStorage.

```typescript
interface ChatConversation {
  id: string
  name: string
  lastInteraction: string
  messages: ChatPersistMessage[]
  documentContent: string
  artifacts?: Artifact[]
  activeArtifactId?: string
}

const {
  conversations,           // ChatConversation[]
  activeConversation,      // ChatConversation | null
  activeConversationId,    // string | null
  createConversation,      // (name?: string) => ChatConversation
  updateConversation,      // (updates: Partial<...>) => void
  renameConversation,      // (id: string, name: string) => void
  deleteConversation,      // (id: string) => void
  switchConversation,      // (id: string) => void
} = useChatPersistence(featureSlug)
```

**Uso:**

```typescript
// Crear nueva conversación
const conv = createConversation("Mi análisis de PRD")

// Actualizar mensaje y artefactos
updateConversation({
  messages: [...messages, newUserMsg, assistantMsg],
  artifacts: [newArtifact],
  documentContent: newContent
})

// Cambiar entre conversaciones
switchConversation(conversationId)
```

### useArtifacts

Gestiona múltiples artefactos dentro de una conversación.

```typescript
const {
  artifacts,                    // Artifact[]
  activeArtifact,              // Artifact | null
  activeArtifactId,            // string | null
  setActiveArtifactId,         // (id: string) => void
  createArtifact,              // (title?, extension?) => string
  deleteArtifact,              // (id: string) => void
  renameArtifact,              // (id: string, newTitle: string) => void
  updateArtifactContent,       // (id: string, content: string) => void
  setArtifactsFromGeneration,  // (newArtifacts: Artifact[]) => void
} = useArtifacts({
  conversationArtifacts: activeConversation?.artifacts ?? [],
  onUpdateConversation: updateConversation
})
```

### useDocumentHistory

Undo/redo para contenido de documentos.

```typescript
const {
  content,      // string (contenido actual)
  stack,        // string[] (historial)
  pointer,      // number (posición en stack)
  canUndo,      // boolean
  canRedo,      // boolean
  isDirty,      // boolean (hay cambios sin guardar)
  
  pushContent,  // (newContent: string) => void
  undo,         // () => void
  redo,         // () => void
  markSaved,    // () => void (resetea isDirty)
  resetHistory  // (newContent: string) => void
} = useDocumentHistory(initialContent, { maxStackSize: 100 })
```

**Uso:**

```typescript
// Al cambiar contenido en el editor
onContentChange={(newContent) => {
  docHistory.pushContent(newContent)
}}

// Ctrl+Z
docHistory.undo()

// Ctrl+Shift+Z
docHistory.redo()

// Guardar
if (docHistory.isDirty) {
  await saveToBackend(docHistory.content)
  docHistory.markSaved()
}
```

### useAgenticGeneration

Orquesta el flujo completo de generación agentic (RAG + LLM + parsing).

```typescript
const {
  isGenerating,          // boolean
  liveThinkingSteps,     // ThinkingStep[] (pasos en tiempo real)
  handleSendMessage,     // (query?: string) => Promise<void>
} = useAgenticGeneration({
  config: featureConfig,
  templateContent: corporateTemplate,
  sources: ["knowledge", "jira"],
  uploaded: uploadedDocs,
  activeConversation,
  activeArtifact,
  artifacts,
  docHistoryContent: docHistory.content,
  onUpdateConversation: updateConversation,
  onSetActiveArtifactId: setActiveArtifactId,
  onDocHistoryPush: docHistory.pushContent,
  onDocHistoryReset: docHistory.resetHistory,
  onSetDocPanelCollapsed: setDocPanelCollapsed,
  onScrollToBottom: scrollToBottom,
  createConversation,
  renameConversation,
})
```

---

## 📄 Componentes Principales

### AgenticDocumentWorkspace

Centro del sistema. Orquesta todo para generar documentos con IA.

```typescript
export const AgenticDocumentWorkspace = ({
  config: FuncionalFeatureConfig,  // Configuración de la feature
  eyebrow?: string,                // Ej: "FUNCIONAL TOOLS"
})
```

**Estructura interna:**

```
AgenticDocumentWorkspace
├─ Sidebar: ChatHistorySidebar (conversaciones previas)
├─ Center: Chat Panel
│  ├─ Chat messages display
│  ├─ Thinking bubble (pasos de generación)
│  └─ Input textarea con maximize
├─ Right: ArtifactsStudio (panel de documentos)
│  ├─ Artifacts list view
│  └─ Document editor view (Univer)
└─ Floating elements: Upload input, Integrations flyout
```

### ArtifactsStudio

Panel derecho que maneja múltiples artefactos.

```typescript
interface ArtifactsStudioProps {
  adapter: UniverAdapter
  artifacts: Artifact[]
  activeArtifactId: string | null
  isCollapsed: boolean
  onToggleCollapse: () => void
  onSelectArtifact: (id: string) => void
  onCreateArtifact: (title?: string, extension?: 'docx' | 'xlsx' | 'txt') => void
  onDeleteArtifact: (id: string) => void
  onRenameArtifact: (id: string, newTitle: string) => void
  onUpdateArtifactContent: (id: string, newContent: string) => void
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
  isDirty: boolean
  isSaving: boolean
}
```

**Estados:**

- `viewMode: 'list'` — Muestra lista de artefactos
- `viewMode: 'editor'` — Muestra editor visual (Univer)
- `isCollapsed: true` — Panel colapsado a barra vertical (11px)

### UniverAdapter

Wrapper para Univer.js (editor de documentos y hojas de cálculo).

```typescript
class UniverAdapter implements IDocumentAdapter {
  async attach(container: HTMLElement, options?): Promise<void>
  async loadTemplate(content: string, kind: 'document' | 'spreadsheet'): Promise<void>
  async exportContent(format: 'docx' | 'xlsx'): Promise<Blob>
  async inspect(): Promise<CanonicalDocumentState>
  async insertText(op: InsertTextOperation): Promise<OperationExecutionResult>
  async insertImage(op: InsertImageOperation): Promise<OperationExecutionResult>
  // ... más operaciones
}
```

---

## 🌐 Cliente HTTP — `api/client.ts`

Wrapper typed de `fetch` con auto-handling de errores.

```typescript
export const api = {
  // Auth
  register: (payload: RegisterPayload) => Promise<AuthResponse>,
  login: (payload: LoginPayload) => Promise<AuthResponse>,
  getMe: () => Promise<{ user: AuthUser }>,
  updateProfile: (payload) => Promise<{ user: AuthUser }>,

  // Features
  generateStandup: (query?: string) => Promise<GroundedResult>,
  askProduct: (payload: FeaturePayload) => Promise<GroundedResult>,
  runPrdChecker: (payload: FeaturePayload) => Promise<GroundedResult>,
  runQaFeature: (featureKey: string, payload) => Promise<GroundedResult>,

  // Document Agent
  agenticPrompt: (payload) => Promise<AgenticPromptResponse>,
  agenticPromptStream: (payload, onChunk) => Promise<AgenticPromptResponse>,
  exportMejorasDocx: (markdown: string, title?: string) => Promise<Blob>,

  // Knowledge
  listDocuments: () => Promise<{ documents: KnowledgeDocument[] }>,
  uploadDocumentsBatch: (files: File[], tags: string) => Promise<...>,
  deleteDocument: (id: string) => Promise<{ ok: boolean }>,
  retrieve: (query: string, sources: string[]) => Promise<...>,

  // Integrations
  getIntegrations: () => Promise<IntegrationInfo[]>,
  startOAuth: (id: string) => Promise<{ authorization_url: string }>,
  connectWithPat: (id: string, payload) => Promise<IntegrationInfo>,
  testIntegration: (id: string) => Promise<TestConnectionResult>,

  // AI Settings
  getAiSettings: () => Promise<AISettings>,
  updateAiSettings: (payload) => Promise<AISettings>,
  getModelCatalog: (refresh?, provider?, task_type?) => Promise<ModelCatalogResponse>,

  // Templates
  getTemplates: () => Promise<{ templates: CorporateTemplate[] }>,
  getTemplateContent: (id: string) => Promise<TemplateDetail>,
  uploadTemplate: (file: File, title?: string) => Promise<{ template }>,
}
```

---

## 🎯 Flujos de Usuario Principales

### Flujo 1: Generar Documento de Mejoras

```
1. Usuario navega a /funcional/mejoras
   ↓
2. MejorasPage → AgenticDocumentWorkspace
   ├─ Carga config de funcionalFeatures.ts
   ├─ Muestra input para prompt
   └─ Panel de artefactos colapsado
   ↓
3. Usuario sube documentos (PDF/DOCX)
   ├─ handlePickFiles() → api.uploadDocumentsBatch()
   └─ uploaded: KnowledgeDocument[]
   ↓
4. Usuario escribe prompt + Enviar
   ├─ handleSendMessage(queryText)
   ├─ Llama api.agenticPromptStream()
   ├─ Renderiza thinking steps en directo
   ├─ Acumula chunks de respuesta
   └─ Parsea <artifact> tags
   ↓
5. Al terminar:
   ├─ Crea Artifact en conversación
   ├─ Renderiza en editor (Univer)
   ├─ Usuario puede editar en directo
   └─ Autosave cada 1.5s
   ↓
6. Usuario descarga:
   └─ handleExport("docx") → api.exportMejorasDocx() → .docx file
```

### Flujo 2: Chat RAG (Ask Product)

```
1. Usuario navega a /conocimiento/ask
   ↓
2. Frontend: carga conversaciones previas de useChatPersistence
   ↓
3. Usuario:
   ├─ Selecciona documentos/fuentes
   ├─ Escribe pregunta
   └─ Presiona Enviar
   ↓
4. Backend:
   ├─ BM25 search en knowledge base
   ├─ Corre LLM con contexto
   └─ Retorna respuesta + citations
   ↓
5. Frontend:
   ├─ Muestra respuesta en chat bubble
   ├─ Renderiza citations como botones
   └─ Persiste en localStorage
```

---

## 🔐 Autenticación en el Frontend

### AuthContext

```typescript
interface AuthContextType {
  user: AuthUser | null
  token: string | null
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (payload: RegisterPayload) => Promise<void>
  logout: () => void
  updateProfile: (payload) => Promise<void>
}

const { user, token, login, logout } = useContext(AuthContext)
```

### Almacenamiento de Token

```typescript
const AUTH_TOKEN_KEY = 'funcassist_auth_token'

// Al login
localStorage.setItem(AUTH_TOKEN_KEY, token)

// En cada request
const getAuthHeaders = () => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}
```

### Rutas Protegidas

```typescript
<Route element={<ProtectedRoute />}>
  {/* Aquí van las rutas protegidas */}
  <Route path="/" element={<DashboardPage />} />
</Route>
```

---

## 📊 Gestión de Estado Global

### Context API

- **AuthContext**: Usuario actual, token, login/logout
- **ToastContext**: Notificaciones (success, error, info)

### localStorage

- **Chat conversations**: `funcassist_chats_{featureSlug}`
- **Auth token**: `funcassist_auth_token`
- **Preferences**: `funcassist_preferences`

### Lifting State Up

Los datos de mayor nivel viven en componentes padres:
- `AgenticDocumentWorkspace` maneja conversaciones, artefactos, historial
- Props fluyen hacia abajo
- Callbacks fluyen hacia arriba

---

## 🧪 Testing Componentes

```bash
# Tipado TypeScript
npm run build

# Linting
npm run lint
```

Usa Storybook para testing en aislamiento (opcional).

---

## 🚀 Build & Deployment

```bash
# Dev server (Vite hot reload)
npm run dev

# Production build
npm run build
# Output: dist/

# Preview production build
npm run preview
```

---

¡Para integración con el backend, consulta [BACKEND.md](./BACKEND.md) y [API_REFERENCE.md](./API_REFERENCE.md)!

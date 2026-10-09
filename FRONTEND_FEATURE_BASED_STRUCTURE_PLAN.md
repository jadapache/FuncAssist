# Implementation Plan: Complete Feature-Based Folder Structure (Frontend)

**Status**: Completed  
**Estimated Effort**: Completed  
**Depends on**: Nothing — purely a structural refactor, zero behavior changes

---

## 1. Goal

Finish migrating the frontend from a **layer-first** structure (group by type: `components/`, `pages/`, `hooks/`) to a **feature-first (vertical slice)** structure (group by domain: `features/knowledge/`, `features/settings/`, etc.).

The transcription feature is the only completed example. Everything else is still flat. This plan completes the migration for all remaining domains.

---

## 2. Current vs Target Structure

### Current (partial — only transcription is done)

```
src/
├── App.tsx
├── api/
│   ├── client.ts
│   ├── index.ts
│   └── modules/
│       ├── aiSettings.ts
│       ├── docAgent.ts
│       ├── drafts.ts
│       ├── features.ts
│       ├── integrations.ts
│       ├── knowledge.ts
│       ├── settings.ts
│       ├── templates.ts
│       └── user.ts
├── components/
│   ├── AppLayout.tsx               ← shell — stays
│   ├── FeatureWorkspace.tsx        ← shared — moves to core/
│   ├── UpdateNotification.tsx      ← shared — stays or moves to core/
│   ├── auth/
│   │   └── ProtectedRoute.tsx      ← stays (global concern)
│   ├── common/                     ← shared UI — stays
│   ├── document_workspace/         ← moves to features/document/
│   ├── integrations/               ← moves to features/integrations/
│   ├── settings/                   ← moves to features/settings/
│   ├── setup/                      ← moves to features/setup/
│   ├── ui/                         ← shared UI — stays
│   └── workspace/                  ← moves to features/document/
├── constants/
│   ├── app.ts                      ← stays (global)
│   ├── funcionalFeatures.ts        ← moves to features/funcional/
│   ├── pmFeatures.ts               ← moves to features/pm/
│   └── qaFeatures.ts               ← moves to features/qa/
├── context/
│   ├── BackgroundJobContext.tsx    ← stays (global)
│   ├── ToastContext.tsx            ← stays (global)
│   └── UserContext.tsx             ← stays (global)
├── core/
│   ├── api/                        ← stays
│   └── providers/                  ← stays
├── document_agent/                 ← moves to features/document/
├── features/
│   └── transcription/              ← DONE — reference pattern
├── hooks/
│   ├── useAgenticGeneration.ts     ← moves to features/document/
│   ├── useAppUpdater.ts            ← stays (global)
│   ├── useArtifacts.ts             ← moves to features/document/
│   ├── useChatPersistence.ts       ← moves to features/document/
│   ├── useCorporateTemplate.ts     ← moves to features/settings/
│   └── useDocumentHistory.ts      ← moves to features/document/
├── pages/
│   ├── DashboardPage.tsx           ← stays (global entry point)
│   ├── configuraciones/            ← moves to features/settings/
│   ├── conocimiento/               ← moves to features/knowledge/
│   ├── funcional/                  ← moves to features/funcional/
│   ├── pm/                         ← moves to features/pm/
│   └── qa/                         ← moves to features/qa/
└── types/
    └── ...                         ← stays (global)
```

### Target

```
src/
├── App.tsx                         ← updated imports only
├── api/                            ← unchanged (global HTTP client)
│   ├── client.ts
│   ├── index.ts
│   └── modules/
├── components/
│   ├── AppLayout.tsx               ← unchanged
│   ├── UpdateNotification.tsx      ← unchanged
│   ├── auth/                       ← unchanged
│   ├── common/                     ← unchanged
│   └── ui/                         ← unchanged
├── constants/
│   └── app.ts                      ← unchanged (global)
├── context/                        ← unchanged (global providers)
├── core/                           ← unchanged
├── features/
│   ├── transcription/              ← DONE (reference)
│   ├── knowledge/                  ← NEW
│   ├── settings/                   ← NEW
│   ├── integrations/               ← NEW
│   ├── document/                   ← NEW
│   ├── pm/                         ← NEW
│   ├── funcional/                  ← NEW
│   ├── qa/                         ← NEW
│   └── setup/                      ← NEW
├── hooks/
│   └── useAppUpdater.ts            ← only global hook stays
├── pages/
│   └── DashboardPage.tsx           ← only global page stays
└── types/
```

---

## 3. Feature Anatomy (Follow the Transcription Pattern)

Every feature follows this internal structure. Only create subdirs that have content:

```
features/{feature}/
├── index.ts              ← public barrel — ONLY export from here externally
├── api/                  ← feature-specific API calls (if needed beyond client.ts)
├── components/           ← all React components owned by this feature
│   └── index.ts          ← components barrel
├── hooks/                ← feature-specific hooks and context
├── pages/                ← routed page components
├── constants/            ← feature-local config, slugs, catalog
├── types/                ← TypeScript types specific to this feature
└── utils/                ← pure utility functions
```

**Rule**: Code outside the feature imports **only** from `features/{feature}/index.ts`. Internal files use relative paths.

---

## 4. Feature Migration Map

### 4.1 `features/knowledge/`

**Sources to move:**

| Current location | Destination |
|---|---|
| `pages/conocimiento/KnowledgePage.tsx` | `features/knowledge/pages/KnowledgePage.tsx` |
| `pages/conocimiento/AskProductPage.tsx` | `features/knowledge/pages/AskProductPage.tsx` |
| `api/modules/knowledge.ts` | `features/knowledge/api/knowledgeApi.ts` |

**New files to create:**

| File | Contents |
|---|---|
| `features/knowledge/index.ts` | Barrel: exports `KnowledgePage`, `AskProductPage` |
| `features/knowledge/pages/index.ts` | Re-exports page components |

**`features/knowledge/index.ts`:**
```typescript
export { KnowledgePage } from './pages/KnowledgePage'
export { AskProductPage } from './pages/AskProductPage'
```

---

### 4.2 `features/settings/`

This is the most file-heavy migration. Settings owns AI model configuration, templates, prompts/rubrics editor, and the profile page.

**Sources to move:**

| Current location | Destination |
|---|---|
| `pages/configuraciones/SettingsPage.tsx` | `features/settings/pages/SettingsPage.tsx` |
| `pages/configuraciones/ProfilePage.tsx` | `features/settings/pages/ProfilePage.tsx` |
| `components/settings/AiModelsPanel.tsx` | `features/settings/components/AiModelsPanel.tsx` |
| `components/settings/AiPromptsRubricsEditor.tsx` | `features/settings/components/AiPromptsRubricsEditor.tsx` |
| `components/settings/IntegrationCard.tsx` | `features/settings/components/IntegrationCard.tsx` |
| `components/settings/IntegrationsPanel.tsx` | `features/settings/components/IntegrationsPanel.tsx` |
| `components/settings/StatusPill.tsx` | `features/settings/components/StatusPill.tsx` |
| `components/settings/TemplatesPanel.tsx` | `features/settings/components/TemplatesPanel.tsx` |
| `components/settings/VoiceAudioSection.tsx` | `features/settings/components/VoiceAudioSection.tsx` |
| `components/settings/WritingModelSection.tsx` | `features/settings/components/WritingModelSection.tsx` |
| `components/settings/hooks/` (entire dir) | `features/settings/hooks/` |
| `components/settings/writing/` (entire dir) | `features/settings/components/writing/` |
| `components/settings/voice/` (entire dir) | `features/settings/components/voice/` |
| `components/settings/templates/` (entire dir) | `features/settings/components/templates/` |
| `components/settings/prompts_rubrics/` (entire dir) | `features/settings/components/prompts_rubrics/` |
| `components/settings/validators/` (entire dir) | `features/settings/validators/` |
| `components/settings/constants.ts` | `features/settings/constants/index.ts` |
| `components/settings/types.ts` | `features/settings/types/index.ts` |
| `hooks/useCorporateTemplate.ts` | `features/settings/hooks/useCorporateTemplate.ts` |
| `api/modules/aiSettings.ts` | `features/settings/api/aiSettingsApi.ts` |
| `api/modules/settings.ts` | `features/settings/api/settingsApi.ts` |
| `api/modules/templates.ts` | `features/settings/api/templatesApi.ts` |

**`features/settings/index.ts`:**
```typescript
// Pages
export { SettingsPage } from './pages/SettingsPage'
export { ProfilePage } from './pages/ProfilePage'

// Panels (consumed by SettingsPage internally — not exposed unless needed outside)
// Components that ARE used externally:
export { IntegrationCard } from './components/IntegrationCard'
export { StatusPill } from './components/StatusPill'
```

---

### 4.3 `features/integrations/`

**Sources to move:**

| Current location | Destination |
|---|---|
| `components/integrations/GitHostingReposPanel.tsx` | `features/integrations/components/GitHostingReposPanel.tsx` |
| `components/integrations/GitHubReposPanel.tsx` | `features/integrations/components/GitHubReposPanel.tsx` |
| `components/integrations/GitOAuthSetup.tsx` | `features/integrations/components/GitOAuthSetup.tsx` |
| `components/integrations/JiraIssuesPreview.tsx` | `features/integrations/components/JiraIssuesPreview.tsx` |
| `components/integrations/JiraOAuthSetup.tsx` | `features/integrations/components/JiraOAuthSetup.tsx` |
| `components/integrations/JiraProjectsPanel.tsx` | `features/integrations/components/JiraProjectsPanel.tsx` |
| `api/modules/integrations.ts` | `features/integrations/api/integrationsApi.ts` |

**`features/integrations/index.ts`:**
```typescript
export { GitHostingReposPanel } from './components/GitHostingReposPanel'
export { GitHubReposPanel } from './components/GitHubReposPanel'
export { GitOAuthSetup } from './components/GitOAuthSetup'
export { JiraIssuesPreview } from './components/JiraIssuesPreview'
export { JiraOAuthSetup } from './components/JiraOAuthSetup'
export { JiraProjectsPanel } from './components/JiraProjectsPanel'
```

---

### 4.4 `features/document/`

This feature owns the agentic document generation workspace, the Univer spreadsheet integration, chat, and the document agent core.

**Sources to move:**

| Current location | Destination |
|---|---|
| `components/workspace/AgenticDocumentWorkspace.tsx` | `features/document/components/AgenticDocumentWorkspace.tsx` |
| `components/workspace/AgenticThinkingBubble.tsx` | `features/document/components/AgenticThinkingBubble.tsx` |
| `components/workspace/ArtifactsStudio.tsx` | `features/document/components/ArtifactsStudio.tsx` |
| `components/workspace/ChatHistorySidebar.tsx` | `features/document/components/ChatHistorySidebar.tsx` |
| `components/workspace/DocumentPanel.tsx` | `features/document/components/DocumentPanel.tsx` |
| `components/document_workspace/` (entire dir) | `features/document/univer/` |
| `components/FeatureWorkspace.tsx` | `features/document/components/FeatureWorkspace.tsx` |
| `document_agent/` (entire dir) | `features/document/agent/` |
| `hooks/useAgenticGeneration.ts` | `features/document/hooks/useAgenticGeneration.ts` |
| `hooks/useArtifacts.ts` | `features/document/hooks/useArtifacts.ts` |
| `hooks/useChatPersistence.ts` | `features/document/hooks/useChatPersistence.ts` |
| `hooks/useDocumentHistory.ts` | `features/document/hooks/useDocumentHistory.ts` |
| `api/modules/docAgent.ts` | `features/document/api/docAgentApi.ts` |
| `api/modules/drafts.ts` | `features/document/api/draftsApi.ts` |

**`features/document/index.ts`:**
```typescript
// Core workspace components used by pm/, funcional/, qa/ feature pages
export { AgenticDocumentWorkspace } from './components/AgenticDocumentWorkspace'
export { FeatureWorkspace } from './components/FeatureWorkspace'
export { ArtifactsStudio } from './components/ArtifactsStudio'
export { DocumentPanel } from './components/DocumentPanel'
export { ChatHistorySidebar } from './components/ChatHistorySidebar'

// Hooks
export { useAgenticGeneration } from './hooks/useAgenticGeneration'
export { useArtifacts } from './hooks/useArtifacts'
export { useChatPersistence } from './hooks/useChatPersistence'
export { useDocumentHistory } from './hooks/useDocumentHistory'
```

---

### 4.5 `features/pm/`

**Sources to move:**

| Current location | Destination |
|---|---|
| `pages/pm/StandupPage.tsx` | `features/pm/pages/StandupPage.tsx` |
| `pages/pm/PmFeaturePage.tsx` | `features/pm/pages/PmFeaturePage.tsx` |
| `constants/pmFeatures.ts` | `features/pm/constants/pmFeatures.ts` |
| `api/modules/features.ts` *(shared with funcional/qa)* | Keep in `api/modules/` — used by multiple features |

**`features/pm/index.ts`:**
```typescript
export { StandupPage } from './pages/StandupPage'
export { PmFeaturePage } from './pages/PmFeaturePage'
export { PM_FEATURES, PM_FEATURE_BY_SLUG } from './constants/pmFeatures'
```

---

### 4.6 `features/funcional/`

**Sources to move:**

| Current location | Destination |
|---|---|
| `pages/funcional/FuncionalFeaturePage.tsx` | `features/funcional/pages/FuncionalFeaturePage.tsx` |
| `pages/funcional/MejorasPage.tsx` | `features/funcional/pages/MejorasPage.tsx` |
| `pages/funcional/LevantamientoPage.tsx` | `features/funcional/pages/LevantamientoPage.tsx` |
| `pages/funcional/InventarioPage.tsx` | `features/funcional/pages/InventarioPage.tsx` |
| `constants/funcionalFeatures.ts` | `features/funcional/constants/funcionalFeatures.ts` |

**Note:** `TranscripcionesPage` is already in `features/transcription/pages/` — leave it there. The Funcional section routes to it via `features/transcription` barrel.

**`features/funcional/index.ts`:**
```typescript
export { FuncionalFeaturePage } from './pages/FuncionalFeaturePage'
export { MejorasPage } from './pages/MejorasPage'
export { LevantamientoPage } from './pages/LevantamientoPage'
export { InventarioPage } from './pages/InventarioPage'
export { FUNCIONAL_FEATURES, FUNCIONAL_FEATURE_BY_SLUG } from './constants/funcionalFeatures'
```

---

### 4.7 `features/qa/`

**Sources to move:**

| Current location | Destination |
|---|---|
| `pages/qa/QaFeaturePage.tsx` | `features/qa/pages/QaFeaturePage.tsx` |
| `constants/qaFeatures.ts` | `features/qa/constants/qaFeatures.ts` |

**`features/qa/index.ts`:**
```typescript
export { QaFeaturePage } from './pages/QaFeaturePage'
export { QA_FEATURES, QA_FEATURE_BY_SLUG } from './constants/qaFeatures'
```

---

### 4.8 `features/setup/`

**Sources to move:**

| Current location | Destination |
|---|---|
| `components/setup/` (entire dir) | `features/setup/components/` |

**`features/setup/index.ts`:**
```typescript
export { FirstTimeSetup } from './components/FirstTimeSetup'
// Add any other setup components
```

---

## 5. Files That Stay in Place

These are either global concerns or used by many features — they do not belong inside any single feature slice:

| File/Dir | Reason |
|---|---|
| `App.tsx` | Root router — orchestrates all features |
| `api/client.ts` | Global typed HTTP client |
| `api/modules/features.ts` | Used by pm, funcional, and qa equally |
| `api/modules/user.ts` | Global user profile |
| `components/AppLayout.tsx` | Shell layout — global |
| `components/UpdateNotification.tsx` | App-level concern |
| `components/auth/ProtectedRoute.tsx` | Global routing guard |
| `components/common/` | Shared UI primitives |
| `components/ui/` | Shared design system components |
| `constants/app.ts` | Global constants (AUTH_TOKEN_KEY, etc.) |
| `context/BackgroundJobContext.tsx` | Global job bus |
| `context/ToastContext.tsx` | Global notification |
| `context/UserContext.tsx` | Global user state |
| `core/` | Error boundaries, global providers |
| `hooks/useAppUpdater.ts` | App-level Tauri updater |
| `pages/DashboardPage.tsx` | Root page — not feature-specific |
| `types/` | Global TypeScript types |

---

## 6. `App.tsx` Import Update

After migration, `App.tsx` imports exclusively from feature barrels:

```typescript
// Before (mixed flat + feature)
import { KnowledgePage } from './pages/conocimiento/KnowledgePage'
import { AskProductPage } from './pages/conocimiento/AskProductPage'
import { SettingsPage } from './pages/configuraciones/SettingsPage'
import { ProfilePage } from './pages/configuraciones/ProfilePage'
import { MejorasPage } from './pages/funcional/MejorasPage'
import { LevantamientoPage } from './pages/funcional/LevantamientoPage'
import { InventarioPage } from './pages/funcional/InventarioPage'
import { FuncionalFeaturePage } from './pages/funcional/FuncionalFeaturePage'
import { StandupPage } from './pages/pm/StandupPage'
import { PmFeaturePage } from './pages/pm/PmFeaturePage'
import { QaFeaturePage } from './pages/qa/QaFeaturePage'
import { AgenticDocumentWorkspace } from './components/workspace/AgenticDocumentWorkspace'

// After (clean feature barrels)
import { KnowledgePage, AskProductPage } from './features/knowledge'
import { SettingsPage, ProfilePage } from './features/settings'
import { MejorasPage, LevantamientoPage, InventarioPage, FuncionalFeaturePage } from './features/funcional'
import { StandupPage, PmFeaturePage } from './features/pm'
import { QaFeaturePage } from './features/qa'
import { TranscripcionesPage, TranscriptionProvider } from './features/transcription'
```

---

## 7. Handling Cross-Feature API Modules

Some modules in `api/modules/` are used by multiple features. The rule is:

| Module | Used by | Decision |
|---|---|---|
| `api/modules/features.ts` | pm, funcional, qa | Keep in `api/modules/` — it IS shared |
| `api/modules/aiSettings.ts` | settings only | Move to `features/settings/api/` |
| `api/modules/knowledge.ts` | knowledge only | Move to `features/knowledge/api/` |
| `api/modules/integrations.ts` | integrations + settings | Keep in `api/modules/` — shared |
| `api/modules/drafts.ts` | document (funcional pages) | Move to `features/document/api/` |
| `api/modules/docAgent.ts` | document only | Move to `features/document/api/` |
| `api/modules/templates.ts` | settings only | Move to `features/settings/api/` |
| `api/modules/settings.ts` | settings only | Move to `features/settings/api/` |
| `api/modules/user.ts` | global (UserContext) | Keep in `api/modules/` |

When a module moves to a feature, update `api/client.ts` to import from the new path, or leave it as an import re-export so existing call sites don't break:

```typescript
// api/modules/aiSettings.ts — becomes a thin re-export shim
// (only if client.ts imports from here and other code has direct imports)
export * from '../../features/settings/api/aiSettingsApi'
```

---

## 8. Task List

### Phase 1 — knowledge (30 min)

- [ ] **K1** Create `features/knowledge/pages/` and move `KnowledgePage.tsx`, `AskProductPage.tsx`
- [ ] **K2** Move `api/modules/knowledge.ts` → `features/knowledge/api/knowledgeApi.ts`
- [ ] **K3** Update internal imports inside moved files
- [ ] **K4** Create `features/knowledge/index.ts` barrel
- [ ] **K5** Update `App.tsx` to import from `features/knowledge`
- [ ] **K6** Delete empty `pages/conocimiento/` directory

### Phase 2 — integrations (30 min)

- [ ] **I1** Create `features/integrations/components/` and move all 6 component files
- [ ] **I2** Move `api/modules/integrations.ts` — if only used by settings, move to `features/integrations/api/`; otherwise keep in `api/modules/`
- [ ] **I3** Update internal imports inside moved files
- [ ] **I4** Create `features/integrations/index.ts` barrel
- [ ] **I5** Update `features/settings/` imports to use `features/integrations` barrel
- [ ] **I6** Delete empty `components/integrations/` directory

### Phase 3 — document (1 hour)

- [ ] **D1** Create `features/document/components/` and move 5 workspace components
- [ ] **D2** Create `features/document/univer/` and move entire `document_workspace/` dir
- [ ] **D3** Create `features/document/agent/` and move entire `document_agent/` dir
- [ ] **D4** Move `FeatureWorkspace.tsx` from `components/` → `features/document/components/`
- [ ] **D5** Move 4 hooks: `useAgenticGeneration`, `useArtifacts`, `useChatPersistence`, `useDocumentHistory`
- [ ] **D6** Move `api/modules/drafts.ts` → `features/document/api/draftsApi.ts`
- [ ] **D7** Move `api/modules/docAgent.ts` → `features/document/api/docAgentApi.ts`
- [ ] **D8** Update all internal cross-imports inside moved files
- [ ] **D9** Create `features/document/index.ts` barrel
- [ ] **D10** Update `features/pm/`, `features/funcional/` imports to use `features/document` barrel
- [ ] **D11** Delete empty `components/workspace/`, `components/document_workspace/`, `document_agent/` directories

### Phase 4 — pm (20 min)

- [ ] **P1** Create `features/pm/pages/` and move `StandupPage.tsx`, `PmFeaturePage.tsx`
- [ ] **P2** Create `features/pm/constants/` and move `constants/pmFeatures.ts`
- [ ] **P3** Update internal imports inside moved files
- [ ] **P4** Create `features/pm/index.ts` barrel
- [ ] **P5** Update `App.tsx` imports
- [ ] **P6** Delete empty `pages/pm/` directory

### Phase 5 — funcional (20 min)

- [ ] **F1** Create `features/funcional/pages/` and move 4 page files
- [ ] **F2** Create `features/funcional/constants/` and move `constants/funcionalFeatures.ts`
- [ ] **F3** Update internal imports inside moved files (reference `features/document` barrel)
- [ ] **F4** Create `features/funcional/index.ts` barrel
- [ ] **F5** Update `App.tsx` imports
- [ ] **F6** Delete empty `pages/funcional/` directory

### Phase 6 — qa (15 min)

- [ ] **Q1** Create `features/qa/pages/` and move `QaFeaturePage.tsx`
- [ ] **Q2** Create `features/qa/constants/` and move `constants/qaFeatures.ts`
- [ ] **Q3** Update internal imports inside moved files
- [ ] **Q4** Create `features/qa/index.ts` barrel
- [ ] **Q5** Update `App.tsx` imports
- [ ] **Q6** Delete empty `pages/qa/` directory

### Phase 7 — settings (1.5 hours — largest)

- [ ] **S1** Create `features/settings/pages/` and move `SettingsPage.tsx`, `ProfilePage.tsx`
- [ ] **S2** Create `features/settings/components/` and move all flat component files from `components/settings/`
- [ ] **S3** Move subdirectories: `writing/`, `voice/`, `templates/`, `prompts_rubrics/`
- [ ] **S4** Create `features/settings/hooks/` and move entire `components/settings/hooks/` dir
- [ ] **S5** Create `features/settings/validators/` and move `components/settings/validators/`
- [ ] **S6** Create `features/settings/types/index.ts` from `components/settings/types.ts`
- [ ] **S7** Create `features/settings/constants/index.ts` from `components/settings/constants.ts`
- [ ] **S8** Move `hooks/useCorporateTemplate.ts` → `features/settings/hooks/`
- [ ] **S9** Move `api/modules/aiSettings.ts`, `settings.ts`, `templates.ts` → `features/settings/api/`
- [ ] **S10** Update all internal imports inside moved files — this is the most tedious step
- [ ] **S11** Create `features/settings/index.ts` barrel
- [ ] **S12** Update `App.tsx` imports
- [ ] **S13** Delete empty `components/settings/` directory and `pages/configuraciones/`

### Phase 8 — setup (10 min)

- [ ] **U1** Create `features/setup/components/` and move entire `components/setup/`
- [ ] **U2** Create `features/setup/index.ts` barrel
- [ ] **U3** Update `App.tsx` or `UserContext.tsx` if they import from `components/setup/`
- [ ] **U4** Delete empty `components/setup/` directory

### Phase 9 — cleanup (20 min)

- [ ] **C1** Confirm `hooks/` only contains `useAppUpdater.ts`
- [ ] **C2** Confirm `constants/` only contains `app.ts`
- [ ] **C3** Confirm `pages/` only contains `DashboardPage.tsx`
- [ ] **C4** Confirm `components/` only contains: `AppLayout.tsx`, `UpdateNotification.tsx`, `auth/`, `common/`, `ui/`
- [ ] **C5** Run `npm run build` — fix any remaining broken imports
- [ ] **C6** Run TypeScript checker: `npx tsc --noEmit` — confirm zero errors
- [ ] **C7** Verify the app runs and all routes load

---

## 9. Import Update Rules

When moving a file, update its imports following this priority:

1. **Imports of global shared code** (`api/client.ts`, `context/`, `components/common/`, `components/ui/`) — update path depth only (e.g. `../../api/client` → `../../../api/client`)

2. **Imports of sibling files in the same feature** — use relative paths (`./`, `../`)

3. **Imports of other features** — use the barrel: `import { X } from '../../document'` NOT `import { X } from '../../document/components/X'`

4. **Never import from inside another feature's internals** — only from its `index.ts`

### Example: moving `MejorasPage.tsx`

```typescript
// Before (in pages/funcional/MejorasPage.tsx)
import { FUNCIONAL_FEATURE_BY_SLUG } from '../../constants/funcionalFeatures'
import { AgenticDocumentWorkspace } from '../../components/workspace/AgenticDocumentWorkspace'

// After (in features/funcional/pages/MejorasPage.tsx)
import { FUNCIONAL_FEATURE_BY_SLUG } from '../constants/funcionalFeatures'
import { AgenticDocumentWorkspace } from '../../document'  // via feature barrel
```

---

## 10. Recommended Execution Order

Work phase by phase, run `npx tsc --noEmit` after each phase before starting the next. This isolates any breakage to a single phase.

| Phase | Scope | Effort | Risk |
|---|---|---|---|
| 1 — knowledge | 2 pages, 1 api module | 30 min | Low |
| 2 — integrations | 6 components | 30 min | Low |
| 4 — pm | 2 pages, 1 constants file | 20 min | Low |
| 5 — funcional | 4 pages, 1 constants file | 20 min | Low |
| 6 — qa | 1 page, 1 constants file | 15 min | Low |
| 3 — document | 5 components, 4 hooks, document_agent, Univer | 1 hour | Medium |
| 8 — setup | 1 dir | 10 min | Low |
| 7 — settings | 10+ components, 1 dir of hooks, 3 api modules | 1.5 hours | High |
| 9 — cleanup | Verify, build, delete dead dirs | 20 min | Low |

**Do settings last** — it has the most files and the most internal cross-imports.

---

## 11. Verification Checklist

- [ ] `npm run build` exits with code 0
- [ ] `npx tsc --noEmit` shows 0 errors
- [ ] All routes render without "Cannot find module" console errors
- [ ] `features/` contains exactly 8 feature dirs: `transcription`, `knowledge`, `settings`, `integrations`, `document`, `pm`, `funcional`, `qa`, `setup`
- [ ] No file outside `features/{name}/` imports from `features/{name}/components/`, `features/{name}/hooks/` — only from `features/{name}/index.ts`
- [ ] `components/` contains only: `AppLayout.tsx`, `UpdateNotification.tsx`, `auth/`, `common/`, `ui/`
- [ ] `pages/` contains only: `DashboardPage.tsx`
- [ ] `hooks/` contains only: `useAppUpdater.ts`
- [ ] `constants/` contains only: `app.ts`

---

**Document Created**: 2026-10-09  
**Version**: 1.0  
**Reference Pattern**: `src/features/transcription/` (completed)

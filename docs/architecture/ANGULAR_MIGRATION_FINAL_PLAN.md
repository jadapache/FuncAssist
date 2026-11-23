# Plan final de implementación — Migración React → Angular (FuncAssist)

**Rama:** `angular-migration`
**Fecha de corte del inventario:** 2026-11-23
**Documentos base:** [`ANGULAR_MIGRATION_IMPLEMENTATION_PLAN.md`](./ANGULAR_MIGRATION_IMPLEMENTATION_PLAN.md) (estrategia) y [`apps/web-angular/MIGRATION_CONVENTIONS.md`](../../apps/web-angular/MIGRATION_CONVENTIONS.md) (reglas de porting).

Este documento lista **lo que ya está hecho**, **lo que falta** (por comparación archivo a archivo entre `frontend/src` y `apps/web-angular/src/app` según el mapeo determinista de las convenciones §2/§7) y el **orden de ejecución** hasta retirar React.

---

## 1. Estado actual (hecho)

| Fase del plan original | Estado | Evidencia |
|---|---|---|
| F3 — Bootstrap Angular, Tailwind, build | ✅ | `apps/web-angular/` (Angular 22 standalone + signals), `angular.json`, `proxy.conf.json` |
| F3 — CI | ✅ | Job `validate-angular` en `.github/workflows/ci.yml` (npm ci, build, test) |
| F3 — Imagen | ✅ (sin validar en despliegue) | `Dockerfile.angular`, `release.yml` modificado |
| F1/F2 — Contratos API y servicios agnósticos | ✅ | `api/client.ts`, `core/api/apiClient.ts`, `features/*/api`, `types`, `utils`, workers, `features/ai/**`, `features/document/agent/**` copiados |
| Core / contextos globales | ✅ | `AuthService`, `UserService`, `ToastService`, `BackgroundJobService`, `SidebarService`, `LoadingService`, `LayoutContextService`, `CurrentUrlService`, guards, `GlobalErrorHandler` (sustituye `ErrorBoundary`) |
| Shared | ✅ | page-header, confirmation-modal, loader, skeletons, markdown, toast-container, floating-job-toast, quick-action-card, directivas lucide/portal/auto-focus |
| Rutas | ✅ | `app.routes.ts` con mismas URLs, lazy loading y `roleGuard` |
| F4 — Login, layout, sidebar, dashboard | ✅ | `features/auth/login-page`, `layout/*`, `features/dashboard/dashboard-page` |
| Integraciones (componentes) | ✅ | git/jira OAuth setup, repos/projects panels, jira-issues-preview |
| Settings (parcial) | 🟡 | hooks/servicios + `integration-card`, `mcp-servers-section`, `provider-credential-card`, `knowledge-base-section`, `writing/*` (4), `status-pill`, `system-config-progress-badge` |
| Chat (parcial) | 🟡 | todos los hooks → servicios, `ChatStore`, `chat-history-sidebar`, `agentic-thinking-bubble`, `artifact-modal`, `inline-artifact-card` |
| Transcripción (parcial) | 🟡 | `TranscriptionStore` + todos los servicios (pipeline, stream, actions, progress, modals), `download-menu`, `segment-list` |
| Documento/Univer (parcial) | 🟡 | `document-history.service`, `univer-floating-toolbar`, `univer-error-boundary`, `univer-rich-text.directive`, `univer-blocks` |
| Tests | 🟡 | 3/3 tests React portados (`templateValidator`, `univerBlockParser`, `transcriptionFeature`) + specs de core/shared |

## 2. Pendiente (inventario)

### 2.1 Páginas aún con placeholder (9 líneas)

| Página Angular | Fuente React | LOC React |
|---|---|---|
| `features/chat/pages/chat-page.component.ts` | `features/chat/pages/ChatPage.tsx` (→ `ChatWorkspace`) | 7 |
| `features/knowledge/pages/knowledge-page.component.ts` | `features/knowledge/pages/KnowledgePage.tsx` | 930 |
| `features/knowledge/pages/ask-product-page.component.ts` | `features/knowledge/pages/AskProductPage.tsx` | 237 |
| `features/settings/pages/settings-page.component.ts` | `features/settings/pages/SettingsPage.tsx` | 196 |
| `features/settings/pages/profile-page.component.ts` | `features/settings/pages/ProfilePage.tsx` | 706 |
| `features/transcription/pages/transcripciones-page.component.ts` | `features/transcription/pages/TranscripcionesPage.tsx` | 421 |

### 2.2 Componentes sin portar

**Shared / comunes** (dominio `shared/`, requiere coordinación):
- `components/common/GroundedResultView.tsx` → `shared/components/grounded-result-view.component.ts` (usado por AskProductPage y FeatureWorkspace).
- `components/ui/StatCard.tsx` → `shared/components/stat-card.component.ts` (usado por ProfilePage).
- `IntegrationTile.tsx`, `TopNav.tsx`: **sin uso** en React → no migrar (eliminar en F10).

**Chat**
- `ChatWorkspace` (509), `ChatInputBar` (474), `ChatMessageList` (187).
- `hooks/useChatPersistence.ts` → verificar si queda lógica no cubierta por `ChatStore` + `features/chat/types/chat.ts`; si no, se declara cubierto.

**Documento / Univer**
- `components/ArtifactsStudio` (572), `DocumentPanel` (348), `FeatureWorkspace` (370).
- `univer/UniverContainer` (1462), `DocumentChatBar` (186), `DocumentInspectorModal` (138).
- `univer/UniverPoCView` (371): sin uso en rutas → **no migrar**; la POC Angular se hace sobre `UniverContainer` (ver F-B).

**Settings**
- Paneles: `AiModelsPanel`, `AIProviderSettings`, `IntegrationsPanel`, `SourceCodeIntegrationsPanel`, `JiraIntegrationCard`, `TemplatesPanel` (378), `UserApprovalsPanel`, `VoiceAudioSection`, `WritingModelSection`, `AiPromptsRubricsEditor`, `ChangePasswordModal`.
- `integrations/`: `IntegrationConfigModal`, `IntegrationLogo`, `IntegrationMarketplaceCard`, `RequestIntegrationModal`.
- `prompts_rubrics/`: `FeatureSelectorSidebar`, `JsonCodeEditor`, `PromptEditor`, `RubricEditor`.
- `templates/`: `TemplateBuilderModal` (254), `TemplatesListSection`, `TemplateTagSidebar`.
- `voice/`: `CloudVoiceModelSelector`, `LocalVoiceModelsList`.

**Transcripción**
- `TranscriptionStudio` (256), `TranscriptionViewer`, `SummaryPanel`, `SummaryModal`, `GenerateModal`, `SpeakerManager`, `UploadArea`, `UploadMediaModal`, `ActiveTranscriptionItem`, `RecentTranscriptionItem`, `VoiceInput` (también usado por Chat).

**Integraciones**
- `GitHubReposPanel.tsx` está cubierto por `github-repos-panel.component.ts` (nombre ya existente; conservarlo). Sin pendientes.

### 2.3 Pendientes transversales
- Validación E2E y de paridad visual (no existe suite E2E Angular).
- Despliegue/coexistencia (`/legacy/*` vs subdominio) sin decidir.
- Decisiones abiertas del plan §14 (sesión, IndexedDB, versión Univer, SLO, rollback).
- Fuga/ciclo de vida de workers WebLLM y Whisper sin prueba.
- Lint/typecheck Angular no están en CI (solo build + test).

---

## 3. Plan de ejecución

Cada bloque sigue las convenciones (mismo markup/clases/copy, `display: contents`, inputs/outputs con nombres idénticos, OnPush). Criterio de “hecho” por bloque: `npx ng build --configuration development` sin errores en el dominio + checklist de paridad del bloque verificado manualmente contra React.

### Bloque A — Shared y Settings/Perfil (P0, ~2 semanas)
Desbloquea las páginas administrativas y deja componentes reutilizados por Knowledge.

1. `shared`: `grounded-result-view`, `stat-card`.
2. Settings hojas: `integrations/*` (4), `voice/*` (2), `prompts_rubrics/*` (4), `templates/*` (3), `change-password-modal`.
3. Settings paneles: `writing-model-section`, `voice-audio-section`, `ai-provider-settings`, `ai-models-panel`, `ai-prompts-rubrics-editor`, `jira-integration-card`, `source-code-integrations-panel`, `integrations-panel`, `templates-panel`, `user-approvals-panel`.
4. Páginas: `settings-page` (tabs vía `?tab=` incluido el redirect de `/integrations`), `profile-page`.

**Aceptación:** matriz §11 “Settings” e “Integrations” (OAuth, PAT, test, disconnect, modelos, credenciales, templates, aprobaciones por rol admin).

### Bloque B — POC Univer (P0 bloqueante para D, ~1 semana, en paralelo con A)
1. Portar `UniverContainer` → `univer-container.component.ts` siguiendo plan §7 (`afterNextRender` para crear, `DestroyRef` para `dispose`), reutilizando `UniverAdapter` existente.
2. Ruta de prueba interna (no expuesta en nav) para validar la checklist §7.4: montaje/desmontaje repetido sin fugas, carga, edición, undo/redo, operaciones canónicas, exportación, navegación fuera de la ruta.
3. Fijar versión Univer (decisión §14.4/5) en `package.json` Angular.

**Aceptación:** POC firmada; sin instancias huérfanas tras 10 ciclos de montaje (heap snapshot).

### Bloque C — Knowledge (P0/P1, ~1.5 semanas)
1. `ask-product-page` (usa `grounded-result-view`).
2. `knowledge-page` (930 LOC): dividir en subcomponentes locales dentro de `features/knowledge/components/` sin alterar markup.

**Aceptación:** upload, batch, listado, borrado, retrieval con citas, permisos por rol (`admin/pm/qa/funcional`), estados loading/empty/error.

### Bloque D — Transcripción (P1, ~2 semanas)
1. Hojas: `upload-area`, `upload-media-modal`, `active-transcription-item`, `recent-transcription-item`, `speaker-manager`, `summary-panel`, `summary-modal`, `generate-modal`, `voice-input`.
2. `transcription-viewer`, `transcription-studio`.
3. `transcripciones-page` (ruta con `:slug`).

**Aceptación:** upload, progreso, SSE con reconexión, polling fallback, cancelación, editor de segmentos, resumen, descarga; jobs sobreviven a navegación (`TranscriptionStore` ya global); worker Whisper sin fugas.

### Bloque E — Chat y documentos (P1, XL, ~3–4 semanas; requiere B y `voice-input` de D)
1. `chat-message-list`, `chat-input-bar` (adjuntos, plantillas corporativas, voz).
2. Documento: `document-inspector-modal`, `document-chat-bar`, `document-panel`, `feature-workspace`, `artifacts-studio` (integra `univer-container`).
3. `chat-workspace` y `chat-page` (ruta `:sessionId`).
4. Confirmar cobertura de `useChatPersistence` (claves `localStorage` idénticas) y cerrar.

**Aceptación:** matriz §11 Chat/Agent/Documents: nueva sesión, historial, streaming, cancelación, errores, intents, tool events, artefactos, operaciones canónicas, autosave, exportación; WebLLM worker singleton que sobrevive a cambios de ruta.

### Bloque F — Calidad y endurecimiento (en paralelo desde A, ~2 semanas efectivas)
1. Añadir lint + typecheck Angular al job `validate-angular`.
2. Suite E2E (Playwright) con los casos de la matriz §11, ejecutable contra React y Angular para comparar.
3. Pruebas de regresión visual por ruta (capturas React vs Angular).
4. Pruebas de memoria de workers (WebLLM, Whisper, Univer).
5. Revisión de bundle: presupuestos en `angular.json`, verificar lazy chunks de Univer/WebLLM.

### Bloque G — Coexistencia y go-live (Fase 9 del plan, ~2–3 semanas)
1. Cerrar decisiones §14 (dominio/ruta, clave de sesión — recomendado: conservar la misma para no invalidar sesiones —, storage, SLO, ventana de rollback).
2. Configurar proxy/despliegue (`frontend-react-legacy` + `frontend-angular`) y validar `Dockerfile.angular`/`release.yml`.
3. Piloto con usuarios internos, monitorización de errores, rollback inmediato verificado.

### Bloque H — Retiro de React (Fase 10)
Ejecutar las tareas de la Fase 10 del plan original. Incluye borrar `IntegrationTile`, `TopNav`, `UniverPoCView` y `Dockerfile` React, y decidir el directorio final (§14.10).

---

## 4. Cronograma estimado (2–3 devs)

| Semana | Dev 1 | Dev 2 | Dev 3 |
|---|---|---|---|
| 1–2 | A (Settings) | B (POC Univer) | F.1–F.2 (CI, E2E base) |
| 3–4 | C (Knowledge) | D (Transcripción) | A cierre + F.3 |
| 5–8 | E (Chat) | E (Documentos/Artifacts) | D cierre + F.4–F.5 |
| 9–11 | G (paridad, piloto) | G | G |
| 12+ | H tras ventana de rollback | | |

Total restante: **~11 semanas + ventana de rollback**.

## 5. Riesgos específicos del tramo restante

| Riesgo | Mitigación |
|---|---|
| `UniverContainer` (1462 LOC) concentra lógica de ciclo de vida | POC aislada (B) antes de E; dividir en servicio `UniverDocumentService` + host |
| `KnowledgePage` (930 LOC) y `ProfilePage` (706 LOC) monolíticos | Subcomponentes locales manteniendo markup exacto |
| `VoiceInput` compartido entre Chat y Transcripción | Portar en D antes de iniciar E |
| Componentes en `shared/` tocados por varios agentes | Asignar `shared/` a un único responsable (Bloque A) |
| Sin E2E, la paridad depende de revisión manual | F.2 arranca en semana 1 |

## 6. Checklist de cierre

- [ ] 0 páginas placeholder.
- [ ] 0 componentes React en uso sin equivalente Angular.
- [ ] Build, lint, typecheck, unit y E2E en verde en CI.
- [ ] POC Univer aceptada y editor integrado sin fugas.
- [ ] Decisiones §14 documentadas.
- [ ] Piloto completado y rollback probado.
- [ ] React/Vite eliminado del pipeline productivo.

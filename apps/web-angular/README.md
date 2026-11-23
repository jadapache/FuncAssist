# FuncAssist — Angular frontend

Angular 22 port of the React/Vite frontend in [`frontend/`](../../frontend/). It targets **identical UI and behaviour**
(same routes, markup, Tailwind classes, API contracts and localStorage keys), as described in
[`docs/architecture/ANGULAR_MIGRATION_IMPLEMENTATION_PLAN.md`](../../docs/architecture/ANGULAR_MIGRATION_IMPLEMENTATION_PLAN.md).
Porting rules used for every component are in [`MIGRATION_CONVENTIONS.md`](./MIGRATION_CONVENTIONS.md).

## Run locally

```bash
npm install
npm start            # ng serve on http://localhost:4200
```

`ng serve` proxies `/api` to `http://127.0.0.1:6728` (the same backend address the React dev build uses; see
`proxy.conf.json`). The backend CORS allowlist does not include port 4200, so always go through the proxy.

From the repository root: `npm run dev:angular`, `npm run build:angular`, `npm run test:angular`.

## Build, type-check and test

```bash
npm run build                         # production build → dist/web-angular/browser
npx ng build --configuration development   # faster type-check (TS + strict templates)
npm test -- --watch=false             # Vitest unit tests (*.spec.ts)
```

Docker: [`Dockerfile.angular`](../../Dockerfile.angular) builds this app and serves it with the same nginx config as React
(`compose.yaml` service `frontend-angular`, port `${ANGULAR_APP_PORT:-6729}`).

## Layout

```text
src/app/
├── api/, core/api/, constants/, types/, utils/, workers/   framework-agnostic contracts copied from React (same relative paths)
├── core/        auth (AuthService, UserService, guards), notifications, loading bar, sidebar/layout state,
│                background jobs, global error handler, current-URL signals
├── shared/      lucide icon directive, markdown renderer, page header, modals, loaders, skeletons, toasts, directives
├── layout/      AppLayout + AppSidebar
└── features/    auth, dashboard, chat, transcription, knowledge, settings, integrations, document, ai
```

React → Angular mapping highlights:

| React | Angular |
|---|---|
| Context providers (`AuthContext`, `UserContext`, `ToastContext`, `BackgroundJobContext`, `ChatContext`, `TranscriptionProvider`, …) | Root services/stores with signals (`core/**`, `features/chat/state/chat.store.ts`, `features/transcription/context/transcription.store.ts`) |
| `<ProtectedRoute allowedRoles>` | `authGuard` / `roleGuard` (`core/auth/auth.guards.ts`) |
| `ErrorBoundary` | `GlobalErrorHandler` + fallback screen in `app.ts` |
| `lucide-react` | vanilla `lucide` icon data rendered by `svg[lucide]` (identical SVG markup) |
| `react-markdown` (no GFM) | `marked` with `gfm: false` + the same per-tag classes |
| Hooks | `@Injectable()` services, provided per component when the hook held local state |

## Environment

`src/environments/environment*.ts`: `apiBase` (empty = same origin, like React without `VITE_API_BASE`) and
`authTokenKey` (`funcassist_auth_token`, shared with React so sessions survive the switch).

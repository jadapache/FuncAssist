import { inject } from '@angular/core'
import { Router, type Routes } from '@angular/router'
import { authGuard, roleGuard } from './core/auth/auth.guards'

/**
 * Route table — same URLs as React `App.tsx`, so bookmarks, OAuth redirects and dashboard links keep working.
 * Every page is lazy loaded (Univer, WebLLM and Whisper only download when their feature is opened).
 */
export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login-page.component').then((m) => m.LoginPageComponent),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./layout/app-layout.component').then((m) => m.AppLayoutComponent),
    children: [
      {
        path: '',
        pathMatch: 'full',
        loadComponent: () =>
          import('./features/dashboard/dashboard-page.component').then((m) => m.DashboardPageComponent),
      },
      {
        path: 'chat',
        loadComponent: () => import('./features/chat/pages/chat-page.component').then((m) => m.ChatPageComponent),
      },
      {
        path: 'chat/:sessionId',
        loadComponent: () => import('./features/chat/pages/chat-page.component').then((m) => m.ChatPageComponent),
      },
      {
        path: 'transcripciones',
        loadComponent: () =>
          import('./features/transcription/pages/transcripciones-page.component').then(
            (m) => m.TranscripcionesPageComponent,
          ),
      },
      {
        path: 'transcripciones/:slug',
        loadComponent: () =>
          import('./features/transcription/pages/transcripciones-page.component').then(
            (m) => m.TranscripcionesPageComponent,
          ),
      },
      {
        path: 'knowledge',
        canActivate: [roleGuard(['admin', 'pm', 'qa', 'funcional'])],
        loadComponent: () =>
          import('./features/knowledge/pages/knowledge-page.component').then((m) => m.KnowledgePageComponent),
      },
      {
        path: 'knowledge/ask',
        canActivate: [roleGuard(['admin', 'pm', 'qa', 'funcional'])],
        loadComponent: () =>
          import('./features/knowledge/pages/ask-product-page.component').then((m) => m.AskProductPageComponent),
      },
      {
        path: 'integrations',
        redirectTo: () => inject(Router).parseUrl('/settings?tab=integrations'),
      },
      {
        path: 'profile',
        loadComponent: () =>
          import('./features/settings/pages/profile-page.component').then((m) => m.ProfilePageComponent),
      },
      {
        path: 'settings',
        loadComponent: () =>
          import('./features/settings/pages/settings-page.component').then((m) => m.SettingsPageComponent),
      },
      { path: '**', redirectTo: '' },
    ],
  },
]

import { ChangeDetectionStrategy, Component, OnInit, computed, input, output, signal } from '@angular/core'
import { RefreshCw } from 'lucide'
import { api } from '../../../api/client'
import type { AuthMethod, IntegrationInfo } from '../../../types'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'
import { GitHostingReposPanelComponent } from '../../integrations/components/git-hosting-repos-panel.component'
import { JiraIssuesPreviewComponent } from '../../integrations/components/jira-issues-preview.component'
import { JiraOAuthSetupComponent } from '../../integrations/components/jira-oauth-setup.component'
import { JiraProjectsPanelComponent } from '../../integrations/components/jira-projects-panel.component'
import { GitOAuthSetupComponent } from '../../integrations/components/git-oauth-setup.component'
import { StatusPillComponent } from './status-pill.component'
import { validatePatPayload } from '../validators/settingsValidation'

/**
 * Port of React `IntegrationCard`.
 *
 * Inputs/outputs keep the React prop names. `onPatConnected` and `onOAuthSaved` are awaited, so they stay
 * function-typed inputs; `onOAuth`, `onDisconnect`, `onTest` and `onError` are outputs.
 *
 * The host IS the React root `<article>` (classes on the host, `role="article"`) because the card is a
 * direct child of a `space-y-6` container in SourceCodeIntegrationsPanel.
 */
@Component({
  selector: 'app-integration-card',
  imports: [
    LucideIconDirective,
    StatusPillComponent,
    JiraProjectsPanelComponent,
    JiraIssuesPreviewComponent,
    GitHostingReposPanelComponent,
    JiraOAuthSetupComponent,
    GitOAuthSetupComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'card border border-[var(--color-border)] p-6 space-y-5',
    role: 'article',
    style: 'display: block',
  },
  template: `
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-xl font-bold text-slate-900">{{ integration().name }}</h2>
        <p class="mt-1 text-sm text-[var(--color-ink-muted)]">{{ integration().description }}</p>
      </div>
      <app-status-pill [connected]="connected()" />
    </div>

    @if (connected()) {
      <div class="rounded-xl bg-slate-50 border border-slate-200/80 p-4 space-y-1.5 text-xs">
        @if (integration().workspace_label) {
          <p>
            <span class="font-semibold text-slate-500">Espacio de trabajo / Workspace: </span>
            <span class="font-mono text-slate-800">{{ integration().workspace_label }}</span>
          </p>
        }
        @if (integration().account_label) {
          <p>
            <span class="font-semibold text-slate-500">Cuenta vinculada: </span>
            <span class="font-medium text-slate-800">{{ integration().account_label }}</span>
          </p>
        }
        @if (integration().details?.['auth_method']) {
          <p>
            <span class="font-semibold text-slate-500">Método de autenticación: </span>
            <span
              class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 uppercase"
              >{{ str(integration().details?.['auth_method']) }}</span
            >
          </p>
        }
      </div>
    }

    <div class="flex flex-wrap gap-3">
      @if (connected()) {
        <button
          type="button"
          (click)="onTest.emit()"
          [disabled]="busy()"
          class="btn-primary text-xs py-2 px-4 disabled:opacity-50 flex items-center gap-1.5 cursor-pointer"
          [attr.aria-label]="'Probar conexión ' + integration().name"
        >
          @if (busy()) {
            <svg [lucide]="icons.RefreshCw" class="h-3.5 w-3.5 animate-spin"></svg>
          }
          <span>Probar conexión</span>
        </button>
        <button
          type="button"
          (click)="onDisconnect.emit()"
          [disabled]="busy()"
          class="rounded-lg border border-[var(--color-bad)] px-4 py-2 text-xs font-semibold text-[var(--color-bad)] hover:bg-red-50 disabled:opacity-50 transition cursor-pointer"
          [attr.aria-label]="'Desconectar ' + integration().name"
        >
          Desconectar
        </button>
        <button
          type="button"
          (click)="showConnectForm.set(true)"
          [disabled]="busy()"
          class="btn-secondary text-xs py-2 px-4 disabled:opacity-50 cursor-pointer"
          [attr.aria-label]="'Cambiar cuenta ' + integration().name"
        >
          Cambiar cuenta
        </button>
      } @else {
        <button
          type="button"
          (click)="showConnectForm.set(true)"
          class="btn-primary text-xs py-2.5 px-5 cursor-pointer"
          [attr.aria-label]="'Conectar ' + integration().name"
        >
          Conectar {{ integration().name }}
        </button>
      }
    </div>

    @if (connected() && integration().id === 'jira') {
      <div class="pt-2 border-t border-[var(--color-border)] space-y-4">
        <app-jira-projects-panel
          [siteUrl]="integration().workspace_label"
          (onSaved)="patConnectedFromPanel()"
          (onError)="onError.emit($event)"
        />
        <app-jira-issues-preview (onError)="onError.emit($event)" />
      </div>
    }

    @if (connected() && integration().id === 'github') {
      <div class="pt-2 border-t border-[var(--color-border)]">
        <app-git-hosting-repos-panel
          integrationId="github"
          heading="Repositorios de GitHub"
          description="Solo los repositorios seleccionados están disponibles para las funciones del sistema. Nada se auto-selecciona."
          (onSaved)="patConnectedFromPanel()"
          (onError)="onError.emit($event)"
        />
      </div>
    }

    @if (connected() && integration().id === 'gitlab') {
      <div class="pt-2 border-t border-[var(--color-border)]">
        <app-git-hosting-repos-panel
          integrationId="gitlab"
          heading="Proyectos de GitLab"
          description="Solo los proyectos seleccionados están disponibles para las funciones del sistema. Nada se auto-selecciona."
          (onSaved)="patConnectedFromPanel()"
          (onError)="onError.emit($event)"
        />
      </div>
    }

    @if (showConnectForm()) {
      <div class="mt-6 border-t border-[var(--color-border)] pt-5 space-y-4">
        <fieldset class="space-y-3">
          <legend class="text-sm font-bold text-slate-800">Método de Autenticación</legend>
          <div class="flex flex-wrap gap-4">
            <label class="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
              <input
                type="radio"
                [name]="integration().id + '-auth'"
                [checked]="authMethod() === 'oauth'"
                (change)="authMethod.set('oauth')"
              />
              <span class="font-semibold text-slate-800">OAuth 2.0</span>
              @if (integration().oauth_configured) {
                <span
                  class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800"
                >
                  Configurado
                </span>
              } @else {
                <span
                  class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800"
                >
                  Requiere configuración
                </span>
              }
            </label>
            <label class="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
              <input
                type="radio"
                [name]="integration().id + '-auth'"
                [checked]="authMethod() === 'pat'"
                (change)="authMethod.set('pat')"
              />
              <span class="font-semibold text-slate-800">Personal Access Token (PAT)</span>
            </label>
          </div>
        </fieldset>

        @if (authMethod() === 'oauth') {
          <div class="mt-4">
            @if (integration().id === 'jira') {
              <app-jira-oauth-setup
                [onSaved]="onOAuthSaved()"
                [onContinueOAuth]="continueOAuth"
                [onCancel]="cancelConnectForm"
              />
            } @else if (integration().id === 'github') {
              <app-git-oauth-setup
                provider="github"
                title="GitHub OAuth"
                docsUrl="https://github.com/settings/developers"
                docsLabel="github.com/settings/developers"
                defaultRedirect="http://127.0.0.1:6728/api/integrations/github/callback"
                [onSaved]="onOAuthSaved()"
                [onContinueOAuth]="continueOAuth"
                [onCancel]="cancelConnectForm"
              />
            } @else if (integration().id === 'gitlab') {
              <app-git-oauth-setup
                provider="gitlab"
                title="GitLab OAuth"
                docsUrl="https://gitlab.com/-/user_settings/applications"
                docsLabel="gitlab.com user applications"
                defaultRedirect="http://127.0.0.1:6728/api/integrations/gitlab/callback"
                [showBaseUrl]="true"
                [onSaved]="onOAuthSaved()"
                [onContinueOAuth]="continueOAuth"
                [onCancel]="cancelConnectForm"
              />
            }
          </div>
        } @else {
          <form class="mt-4 space-y-3" (submit)="handlePatSubmit($event)">
            @if (integration().id === 'jira') {
              <p class="text-xs text-[var(--color-ink-muted)]">
                Recomendado para entornos de desarrollo. Crea tu token en
                <a
                  href="https://id.atlassian.com/manage-profile/security/api-tokens"
                  target="_blank"
                  rel="noreferrer"
                  class="text-[#002777] font-semibold underline hover:text-[#004497]"
                  >id.atlassian.com → Security → API tokens</a
                >.
              </p>
              <label class="block text-sm">
                <span class="mb-1 block text-xs font-semibold text-slate-700">Correo de Atlassian</span>
                <input
                  required
                  type="email"
                  [value]="email()"
                  (input)="email.set($any($event.target).value)"
                  class="input-field"
                  placeholder="usuario@organizacion.com"
                  aria-label="Correo de Atlassian"
                />
              </label>
              <label class="block text-sm">
                <span class="mb-1 block text-xs font-semibold text-slate-700">
                  URL del Sitio Jira (ejemplo: https://mi-dominio.atlassian.net)
                </span>
                <input
                  required
                  type="url"
                  [value]="baseUrl()"
                  (input)="baseUrl.set($any($event.target).value)"
                  class="input-field"
                  placeholder="https://empresa.atlassian.net"
                  aria-label="URL del sitio Jira"
                />
              </label>
            }
            @if (integration().id === 'gitlab') {
              <label class="block text-sm">
                <span class="mb-1 block text-xs font-semibold text-slate-700">
                  URL de GitLab (opcional — por defecto https://gitlab.com)
                </span>
                <input
                  type="url"
                  [value]="baseUrl()"
                  (input)="baseUrl.set($any($event.target).value)"
                  placeholder="https://gitlab.com"
                  class="input-field"
                  aria-label="URL de GitLab"
                />
              </label>
            }
            <label class="block text-sm">
              <span class="mb-1 block text-xs font-semibold text-slate-700">Personal Access Token (PAT)</span>
              <input
                required
                type="password"
                [value]="token()"
                (input)="token.set($any($event.target).value)"
                class="input-field font-mono"
                placeholder="ghp_..., glpat-..., etc."
                [attr.aria-label]="'Token de acceso personal de ' + integration().name"
              />
            </label>
            <div class="flex flex-wrap gap-3 pt-1">
              <button
                type="submit"
                [disabled]="submitting()"
                class="btn-primary text-xs py-2 px-4 disabled:opacity-50 cursor-pointer"
              >
                {{ submitting() ? 'Conectando…' : 'Guardar conexión' }}
              </button>
              <button
                type="button"
                (click)="showConnectForm.set(false)"
                class="btn-secondary text-xs py-2 px-4 cursor-pointer"
              >
                Cancelar
              </button>
            </div>
          </form>
        }
      </div>
    }
  `,
})
export class IntegrationCardComponent implements OnInit {
  readonly integration = input.required<IntegrationInfo>()
  readonly busy = input.required<boolean>()
  readonly onPatConnected = input.required<() => Promise<void>>()
  readonly onOAuthSaved = input.required<() => Promise<void>>()

  readonly onOAuth = output<void>()
  readonly onDisconnect = output<void>()
  readonly onTest = output<void>()
  readonly onError = output<string>()

  protected readonly icons = { RefreshCw }
  protected readonly str = String

  protected readonly connected = computed(() => this.integration().status === 'connected')
  protected readonly authMethod = signal<AuthMethod>('oauth')
  protected readonly showConnectForm = signal(false)
  protected readonly token = signal('')
  protected readonly email = signal('')
  protected readonly baseUrl = signal('')
  protected readonly submitting = signal(false)

  /** Stable callbacks handed to the OAuth setup components (React passed `onOAuth` / an inline closure). */
  protected readonly continueOAuth = (): void => this.onOAuth.emit()
  protected readonly cancelConnectForm = (): void => this.showConnectForm.set(false)

  ngOnInit(): void {
    // useState<AuthMethod>(integration.id === 'jira' ? 'pat' : 'oauth')
    this.authMethod.set(this.integration().id === 'jira' ? 'pat' : 'oauth')
  }

  protected patConnectedFromPanel(): void {
    void this.onPatConnected()()
  }

  protected async handlePatSubmit(event: Event): Promise<void> {
    event.preventDefault()
    const integration = this.integration()
    const token = this.token()
    const email = this.email()
    const baseUrl = this.baseUrl()

    const validation = validatePatPayload(integration.id, {
      token,
      email: email || undefined,
      baseUrl: baseUrl || undefined,
    })

    if (!validation.isValid) {
      this.onError.emit(validation.error || 'Verifica los campos ingresados para la conexión con PAT.')
      return
    }

    this.submitting.set(true)
    try {
      await api.connectWithPat(integration.id, {
        token: token.trim(),
        email: email ? email.trim() : undefined,
        base_url: baseUrl ? baseUrl.trim() : undefined,
      })
      this.showConnectForm.set(false)
      this.token.set('')
      await this.onPatConnected()()
    } catch (err) {
      this.onError.emit(err instanceof Error ? err.message : 'Error al conectar mediante PAT')
    } finally {
      this.submitting.set(false)
    }
  }
}

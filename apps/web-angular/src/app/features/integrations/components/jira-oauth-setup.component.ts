import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, signal } from '@angular/core'
import { CheckCircle2, ChevronDown, ChevronUp, ExternalLink, HelpCircle, Key, Lock, Settings } from 'lucide'
import { api } from '../../../api/client'
import { ToastService } from '../../../core/notifications/toast.service'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'

type ScopeGuideItem = {
  scope: string
  label: string
  where: string
  required: boolean
}

type JiraOAuthStatus = {
  configured: boolean
  client_id_set: boolean
  client_secret_set: boolean
  redirect_uri: string
  scopes?: string[]
  scope_guide?: ScopeGuideItem[]
}

/**
 * Port of React `JiraOAuthSetup`.
 *
 * `onSaved` is awaited and `onContinueOAuth` / `onCancel` change the markup depending on whether they
 * were passed, so the three callbacks stay function-typed inputs (same names as the React props).
 */
@Component({
  selector: 'app-jira-oauth-setup',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    @if (status()?.configured && !isEditing()) {
      <div class="rounded-xl border border-blue-200 bg-blue-50/50 p-4 space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <svg [lucide]="icons.CheckCircle2" class="h-4 w-4 text-emerald-600 shrink-0"></svg>
            <span class="text-xs font-semibold text-slate-900">Credenciales OAuth 2.0 registradas para Jira Software</span>
          </div>
          <button
            type="button"
            (click)="isEditing.set(true)"
            class="inline-flex items-center gap-1 text-xs text-[#002777] hover:underline font-semibold cursor-pointer"
          >
            <svg [lucide]="icons.Settings" class="h-3.5 w-3.5"></svg>
            <span>Modificar credenciales</span>
          </button>
        </div>

        <div class="text-xs text-slate-600 space-y-1">
          <p>
            <span class="font-medium text-slate-500">Redirect URI / Callback URL: </span>
            <code class="rounded bg-white px-1.5 py-0.5 border border-slate-200 font-mono text-[11px] text-slate-800">{{ status()!.redirect_uri }}</code>
          </p>
          <p>
            <span class="font-medium text-slate-500">Permisos activos: </span>
            <span class="font-mono text-[11px] text-slate-700">{{ activeScopes().join(', ') }}</span>
          </p>
        </div>

        <div class="flex flex-wrap items-center gap-2.5 pt-1">
          @if (onContinueOAuth()) {
            <button
              type="button"
              (click)="onContinueOAuth()!()"
              [disabled]="busy()"
              class="btn-primary text-xs py-2 px-4 cursor-pointer"
            >
              Continuar con OAuth
            </button>
          }
          <button
            type="button"
            (click)="showGuide.set(!showGuide())"
            class="btn-secondary text-xs py-2 px-3 inline-flex items-center gap-1 cursor-pointer"
          >
            <svg [lucide]="icons.HelpCircle" class="h-3.5 w-3.5 text-slate-500"></svg>
            <span>{{ showGuide() ? 'Ocultar guía de permisos' : 'Guía de permisos Atlassian' }}</span>
          </button>
          @if (onCancel()) {
            <button type="button" (click)="onCancel()!()" class="btn-secondary text-xs py-2 px-4 cursor-pointer">
              Cancelar
            </button>
          }
        </div>

        <!-- Guía desplegable de permisos si está activo -->
        @if (showGuide()) {
          <div class="mt-3 rounded-lg border border-slate-200 bg-white p-3 text-xs space-y-2">
            <h4 class="font-bold text-slate-800">Checklist para Atlassian Developer Console:</h4>
            <ol class="list-decimal space-y-1 pl-4 text-slate-600">
              <li>
                Accede a
                <a
                  href="https://developer.atlassian.com/console/myapps/"
                  target="_blank"
                  rel="noreferrer"
                  class="text-[#002777] font-semibold underline"
                  >developer.atlassian.com/console/myapps</a
                >
                y selecciona tu app OAuth 2.0 (3LO).
              </li>
              <li>
                En <strong>Authorization</strong> → OAuth 2.0 (3LO) → Callback URL: añade
                <code class="bg-slate-100 px-1 py-0.5 rounded">{{ status()!.redirect_uri }}</code>.
              </li>
              <li>
                En <strong>Permissions</strong> → añade <em>Jira API</em> (y <em>Jira Software API</em>) y habilita los scopes solicitados.
              </li>
              <li>Debes iniciar sesión con la misma cuenta de Atlassian que creó la app.</li>
            </ol>
          </div>
        }
      </div>
    } @else {
      <div class="space-y-4 rounded-xl border border-slate-200 bg-slate-50/70 p-4">
        <!-- Encabezado y toggle de guía -->
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-1.5">
              <svg [lucide]="icons.Key" class="h-3.5 w-3.5 text-[#002777]"></svg>
              Configuración de Credenciales OAuth 2.0 (Jira Software)
            </h3>
            <p class="mt-1 text-xs text-[var(--color-ink-muted)]">
              Obtén el Client ID y Client Secret desde la pestaña <strong>Settings</strong> de tu app en
              <a
                href="https://developer.atlassian.com/console/myapps/"
                target="_blank"
                rel="noreferrer"
                class="text-[#002777] font-semibold underline hover:text-[#004497] inline-flex items-center gap-0.5"
                >Atlassian Developer Console<svg [lucide]="icons.ExternalLink" class="h-2.5 w-2.5"></svg></a
              >.
            </p>
          </div>

          <div class="flex items-center gap-2">
            <button
              type="button"
              (click)="showGuide.set(!showGuide())"
              class="inline-flex items-center gap-1 text-xs font-semibold text-[#002777] hover:underline cursor-pointer"
            >
              @if (showGuide()) {
                <svg [lucide]="icons.ChevronUp" class="h-3.5 w-3.5"></svg>
              } @else {
                <svg [lucide]="icons.ChevronDown" class="h-3.5 w-3.5"></svg>
              }
              <span>{{ showGuide() ? 'Ocultar guía Atlassian' : 'Ver checklist y permisos' }}</span>
            </button>
            @if (status()?.configured && isEditing()) {
              <button
                type="button"
                (click)="isEditing.set(false)"
                class="text-xs text-slate-500 hover:text-slate-800 underline cursor-pointer"
              >
                Cancelar edición
              </button>
            }
          </div>
        </div>

        <!-- Guía desplegable de Atlassian -->
        @if (showGuide()) {
          <div class="rounded-lg border border-slate-200 bg-white p-3.5 text-xs space-y-3">
            <h4 class="font-bold text-slate-800">Checklist para Atlassian Developer Console:</h4>
            <ol class="list-decimal space-y-1.5 pl-4 text-slate-600">
              <li>
                Abre
                <a
                  href="https://developer.atlassian.com/console/myapps/"
                  target="_blank"
                  rel="noreferrer"
                  class="text-[#002777] font-semibold underline"
                  >developer.atlassian.com/console/myapps</a
                >
                y selecciona tu aplicación OAuth 2.0.
              </li>
              <li>
                En <strong>Authorization</strong> → OAuth 2.0 (3LO) → define el Callback URL exactamente como:
                <code class="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] text-slate-800">{{ redirectUri() }}</code>
              </li>
              <li>
                En <strong>Permissions</strong> → añade <em>Jira API</em> (y <em>Jira Software API</em> si necesitas sprints/tableros) y activa los permisos necesarios.
              </li>
              <li>Inicia sesión con la misma cuenta Atlassian propietaria de la aplicación en modo desarrollo.</li>
            </ol>

            @if (scopeGuide().length) {
              <div class="mt-2 overflow-x-auto border-t border-slate-100 pt-2">
                <table class="w-full text-left text-[11px]">
                  <thead>
                    <tr class="border-b border-slate-200 text-slate-500 font-semibold">
                      <th class="py-1 pr-2">Permiso / Scope</th>
                      <th class="py-1 pr-2">Ubicación en Consola</th>
                      <th class="py-1">Requerido</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100">
                    @for (item of scopeGuide(); track item.scope) {
                      <tr>
                        <td class="py-1 pr-2">
                          <code class="font-mono text-slate-800">{{ item.scope }}</code>
                          <div class="text-[10px] text-slate-400">{{ item.label }}</div>
                        </td>
                        <td class="py-1 pr-2 text-slate-500">{{ item.where }}</td>
                        <td class="py-1">
                          @if (activeScopes().includes(item.scope)) {
                            <span class="font-semibold text-emerald-600">Sí</span>
                          } @else {
                            <span class="text-slate-400">Opcional</span>
                          }
                        </td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            }
          </div>
        }

        <!-- Formulario de inputs -->
        <form (submit)="handleSubmit($event, false)" class="space-y-3">
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="block text-sm">
              <span class="mb-1 block text-xs font-semibold text-slate-700">
                Client ID de Jira <span class="text-red-500">*</span>
              </span>
              <input
                required
                [value]="clientId()"
                (input)="clientId.set($any($event.target).value)"
                class="input-field text-xs"
                [placeholder]="status()?.client_id_set ? 'Client ID guardado' : 'Ej: aBcDe12345...'"
                aria-label="Client ID de Jira"
              />
            </label>

            <label class="block text-sm">
              <span class="mb-1 block text-xs font-semibold text-slate-700">
                Client Secret de Jira <span class="text-red-500">*</span>
              </span>
              <div class="relative">
                <input
                  [required]="!status()?.client_secret_set"
                  type="password"
                  [value]="clientSecret()"
                  (input)="clientSecret.set($any($event.target).value)"
                  class="input-field text-xs"
                  [placeholder]="status()?.client_secret_set ? '•••• guardado — deja en blanco para mantener' : 'Ej: ATOA...'"
                  aria-label="Client Secret de Jira"
                />
                <svg
                  [lucide]="icons.Lock"
                  class="absolute right-3 top-2.5 h-3.5 w-3.5 text-slate-400 pointer-events-none"
                ></svg>
              </div>
            </label>
          </div>

          <label class="block text-sm">
            <span class="mb-1 block text-xs font-semibold text-slate-700">
              Redirect URI (debe coincidir con Atlassian) <span class="text-red-500">*</span>
            </span>
            <input
              required
              [value]="redirectUri()"
              (input)="redirectUri.set($any($event.target).value)"
              class="input-field font-mono text-xs text-slate-800"
              aria-label="Redirect URI de Jira"
            />
          </label>

          @if (error()) {
            <p class="alert-error text-xs">{{ error() }}</p>
          }

          <div class="flex flex-wrap items-center gap-2.5 pt-1">
            @if (onContinueOAuth()) {
              <button
                type="button"
                (click)="handleSubmit($event, true)"
                [disabled]="busy() || (!clientId() && !status()?.client_id_set)"
                class="btn-primary text-xs py-2 px-4 disabled:opacity-50 cursor-pointer"
              >
                {{ busy() ? 'Guardando…' : 'Guardar y Continuar con OAuth' }}
              </button>
            }

            <button
              type="submit"
              [disabled]="busy() || (!clientId() && !status()?.client_id_set)"
              class="btn-secondary text-xs py-2 px-4 disabled:opacity-50 cursor-pointer"
            >
              {{ busy() ? 'Guardando…' : 'Guardar Credenciales' }}
            </button>

            @if (isEditing()) {
              <button
                type="button"
                (click)="isEditing.set(false)"
                class="text-xs text-slate-500 hover:text-slate-700 px-2 py-1 cursor-pointer"
              >
                Cancelar
              </button>
            } @else if (onCancel()) {
              <button type="button" (click)="onCancel()!()" class="btn-secondary text-xs py-2 px-4 cursor-pointer">
                Cancelar
              </button>
            }
          </div>
        </form>
      </div>
    }
  `,
})
export class JiraOAuthSetupComponent implements OnInit {
  private readonly toastService = inject(ToastService)

  readonly onSaved = input.required<() => void | Promise<void>>()
  readonly onContinueOAuth = input<(() => void) | undefined>(undefined)
  readonly onCancel = input<(() => void) | undefined>(undefined)

  protected readonly icons = { CheckCircle2, ChevronDown, ChevronUp, ExternalLink, HelpCircle, Key, Lock, Settings }

  protected readonly status = signal<JiraOAuthStatus | null>(null)
  protected readonly clientId = signal('')
  protected readonly clientSecret = signal('')
  protected readonly redirectUri = signal('http://127.0.0.1:6728/api/integrations/jira/callback')
  protected readonly busy = signal(false)
  protected readonly isEditing = signal(false)
  protected readonly error = signal<string | null>(null)
  protected readonly showGuide = signal(false)

  protected readonly activeScopes = computed(() => this.status()?.scopes ?? ['read:jira-work', 'offline_access'])
  protected readonly scopeGuide = computed(() => this.status()?.scope_guide ?? [])

  ngOnInit(): void {
    void this.load()
  }

  private async load(): Promise<void> {
    try {
      const data = await api.getJiraOAuth()
      this.status.set(data)
      this.redirectUri.set(data.redirect_uri)
    } catch {
      // Ignorar error inicial
    }
  }

  private async saveCredentials(): Promise<boolean> {
    this.busy.set(true)
    this.error.set(null)
    try {
      await api.saveJiraOAuth({
        client_id: this.clientId(),
        client_secret: this.clientSecret() || undefined,
        redirect_uri: this.redirectUri(),
      })
      await this.load()
      this.clientSecret.set('')
      this.isEditing.set(false)
      this.toastService.toast.success('Configuración OAuth de Jira guardada con éxito.')
      await this.onSaved()()
      return true
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al guardar la configuración OAuth de Jira'
      this.error.set(msg)
      this.toastService.toast.error(msg)
      return false
    } finally {
      this.busy.set(false)
    }
  }

  protected async handleSubmit(event: Event, andConnect = false): Promise<void> {
    event.preventDefault()
    const success = await this.saveCredentials()
    const onContinueOAuth = this.onContinueOAuth()
    if (success && andConnect && onContinueOAuth) {
      onContinueOAuth()
    }
  }
}

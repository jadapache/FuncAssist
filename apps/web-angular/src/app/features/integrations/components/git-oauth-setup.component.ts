import { ChangeDetectionStrategy, Component, OnInit, effect, inject, input, signal, untracked } from '@angular/core'
import { CheckCircle2, ExternalLink, Key, Lock, Settings } from 'lucide'
import { api } from '../../../api/client'
import { ToastService } from '../../../core/notifications/toast.service'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'

type OAuthStatus = {
  configured: boolean
  client_id_set: boolean
  client_secret_set: boolean
  redirect_uri: string
  base_url?: string
}

/**
 * Port of React `OAuthSetup` (exported as `GitOAuthSetup`).
 *
 * `onSaved` is awaited and `onContinueOAuth` / `onCancel` change the markup depending on whether they
 * were passed, so the three callbacks stay function-typed inputs (same names as the React props).
 */
@Component({
  selector: 'app-git-oauth-setup',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    @if (status()?.configured && !isEditing()) {
      <div class="rounded-xl border border-blue-200 bg-blue-50/50 p-4 space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <svg [lucide]="icons.CheckCircle2" class="h-4 w-4 text-emerald-600 shrink-0"></svg>
            <span class="text-xs font-semibold text-slate-900">
              Credenciales OAuth 2.0 registradas para {{ providerLabel() }}
            </span>
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
            <code class="rounded bg-white px-1.5 py-0.5 border border-slate-200 font-mono text-[11px] text-slate-800">{{
              status()!.redirect_uri
            }}</code>
          </p>
          @if (showBaseUrl() && status()!.base_url) {
            <p>
              <span class="font-medium text-slate-500">URL Instancia: </span>
              <span class="font-mono text-slate-800">{{ status()!.base_url }}</span>
            </p>
          }
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
          @if (onCancel()) {
            <button type="button" (click)="onCancel()!()" class="btn-secondary text-xs py-2 px-4 cursor-pointer">
              Cancelar
            </button>
          }
        </div>
      </div>
    } @else {
      <form (submit)="handleSubmit($event, false)" class="space-y-4 rounded-xl border border-slate-200 bg-slate-50/70 p-4">
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-1.5">
              <svg [lucide]="icons.Key" class="h-3.5 w-3.5 text-[#002777]"></svg>
              Configuración de Credenciales OAuth 2.0 ({{ providerLabel() }})
            </h3>
            <p class="mt-1 text-xs text-[var(--color-ink-muted)]">
              Crea una aplicación OAuth en
              <a
                [href]="docsUrl()"
                target="_blank"
                rel="noreferrer"
                class="text-[#002777] font-semibold underline hover:text-[#004497] inline-flex items-center gap-0.5"
              >{{ docsLabel() }}<svg [lucide]="icons.ExternalLink" class="h-2.5 w-2.5"></svg></a>
              e ingresa la URL de callback (Redirect URI) exactamente como se indica abajo.
            </p>
          </div>

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

        @if (showBaseUrl()) {
          <label class="block text-sm">
            <span class="mb-1 block text-xs font-semibold text-slate-700">
              URL de la Instancia GitLab (opcional — por defecto https://gitlab.com)
            </span>
            <input
              [value]="baseUrl()"
              (input)="baseUrl.set($any($event.target).value)"
              class="input-field text-xs"
              placeholder="https://gitlab.com"
              aria-label="URL de la Instancia GitLab"
            />
          </label>
        }

        <div class="grid gap-3 sm:grid-cols-2">
          <label class="block text-sm">
            <span class="mb-1 block text-xs font-semibold text-slate-700">
              Client ID / Application ID <span class="text-red-500">*</span>
            </span>
            <input
              required
              [value]="clientId()"
              (input)="clientId.set($any($event.target).value)"
              class="input-field text-xs"
              [placeholder]="status()?.client_id_set ? 'Client ID guardado' : 'Ej: Ov23li...'"
              [attr.aria-label]="title() + ' Client ID'"
            />
          </label>

          <label class="block text-sm">
            <span class="mb-1 block text-xs font-semibold text-slate-700">
              Client Secret <span class="text-red-500">*</span>
            </span>
            <div class="relative">
              <input
                [required]="!status()?.client_secret_set"
                type="password"
                [value]="clientSecret()"
                (input)="clientSecret.set($any($event.target).value)"
                class="input-field text-xs"
                [placeholder]="status()?.client_secret_set ? '•••• guardado — deja en blanco para mantener' : 'Ej: sec_...'"
                [attr.aria-label]="title() + ' Client Secret'"
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
            Redirect URI / URL de Callback (Debe coincidir en {{ providerLabel() }}) <span class="text-red-500">*</span>
          </span>
          <input
            required
            [value]="redirectUri()"
            (input)="redirectUri.set($any($event.target).value)"
            class="input-field font-mono text-xs text-slate-800"
            [attr.aria-label]="title() + ' Redirect URI'"
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
    }
  `,
})
export class GitOAuthSetupComponent implements OnInit {
  private readonly toastService = inject(ToastService)

  readonly provider = input.required<'github' | 'gitlab'>()
  readonly title = input.required<string>()
  readonly docsUrl = input.required<string>()
  readonly docsLabel = input.required<string>()
  readonly defaultRedirect = input.required<string>()
  readonly showBaseUrl = input(false)
  readonly defaultBaseUrl = input('https://gitlab.com')
  readonly onSaved = input.required<() => void | Promise<void>>()
  readonly onContinueOAuth = input<(() => void) | undefined>(undefined)
  readonly onCancel = input<(() => void) | undefined>(undefined)

  protected readonly icons = { CheckCircle2, ExternalLink, Key, Lock, Settings }

  protected readonly status = signal<OAuthStatus | null>(null)
  protected readonly clientId = signal('')
  protected readonly clientSecret = signal('')
  protected readonly redirectUri = signal('')
  protected readonly baseUrl = signal('')
  protected readonly busy = signal(false)
  protected readonly isEditing = signal(false)
  protected readonly error = signal<string | null>(null)

  constructor() {
    // useEffect(() => { load() }, [provider])
    effect(() => {
      this.provider()
      untracked(() => void this.load())
    })
  }

  ngOnInit(): void {
    // useState(defaultRedirect) / useState(defaultBaseUrl)
    this.redirectUri.set(this.defaultRedirect())
    this.baseUrl.set(this.defaultBaseUrl())
  }

  protected providerLabel(): string {
    return this.provider() === 'github' ? 'GitHub' : 'GitLab'
  }

  private async load(): Promise<void> {
    try {
      const data = this.provider() === 'github' ? await api.getGitHubOAuth() : await api.getGitLabOAuth()
      this.status.set(data)
      this.redirectUri.set(data.redirect_uri || this.defaultRedirect())
      if ('base_url' in data && typeof data.base_url === 'string') {
        this.baseUrl.set(data.base_url)
      }
    } catch {
      // Ignorar error inicial de carga
    }
  }

  private async saveCredentials(): Promise<boolean> {
    const providerLabel = this.providerLabel()
    this.busy.set(true)
    this.error.set(null)
    try {
      if (this.provider() === 'github') {
        await api.saveGitHubOAuth({
          client_id: this.clientId(),
          client_secret: this.clientSecret() || undefined,
          redirect_uri: this.redirectUri(),
        })
      } else {
        await api.saveGitLabOAuth({
          client_id: this.clientId(),
          client_secret: this.clientSecret() || undefined,
          redirect_uri: this.redirectUri(),
          base_url: this.baseUrl() || undefined,
        })
      }
      await this.load()
      this.clientSecret.set('')
      this.isEditing.set(false)
      this.toastService.toast.success(`Credenciales OAuth de ${providerLabel} guardadas con éxito.`)
      await this.onSaved()()
      return true
    } catch (err) {
      const msg = err instanceof Error ? err.message : `Error al guardar configuración OAuth de ${providerLabel}`
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

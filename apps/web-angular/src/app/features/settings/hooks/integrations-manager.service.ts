import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core'
import { Router } from '@angular/router'
import { api } from '../../../api/client'
import type { IntegrationInfo } from '../../../types'
import { ToastService } from '../../../core/notifications/toast.service'
import { CurrentUrlService } from '../../../core/layout/current-url.service'

export type IntegrationsManagerOptions = {
  /** Same as the React hook option. Accepts a plain boolean or a reactive getter (e.g. a signal/computed). */
  enabled?: boolean | (() => boolean)
}

/**
 * Angular port of React `useIntegrationsManager(options?)`.
 *
 * `@Injectable()` without `providedIn`: list it in the consuming component's `providers`
 * (one instance per component, like a hook call).
 *
 * Hook option → `configure({ enabled })` (boolean or signal/getter). Call it from the consumer's
 * constructor / field initializer so the first load already honours it. `setEnabled(bool)` is a shortcut.
 * Default: enabled = true (same as the hook).
 *
 * Public members (same names as the hook's return object):
 * - State (signals, read with `()`): `integrations`, `loadingIntegrations`, `busyIntegrationId`,
 *   `jira`, `github`, `gitlab`, `connectedCount`
 * - Methods: `loadIntegrations()`, `handlePatConnected(id, label)`, `handleOAuthConnect(id)`,
 *   `handleDisconnect(id)`, `handleTest(id)`
 *
 * Side effects (same as the hook): loads integrations whenever it becomes enabled, and handles the
 * OAuth callback query params (`?jira|github|gitlab=connected|error&message=…`), showing the toast and
 * replacing the query string with `?tab=integrations`.
 */
@Injectable()
export class IntegrationsManagerService {
  private readonly toastService = inject(ToastService)
  private readonly router = inject(Router)
  private readonly currentUrl = inject(CurrentUrlService)

  private readonly _integrations = signal<IntegrationInfo[]>([])
  private readonly _loadingIntegrations = signal(false)
  private readonly _busyIntegrationId = signal<string | null>(null)
  private readonly enabledSource = signal<() => boolean>(() => true)
  private readonly isEnabled = computed(() => this.enabledSource()())

  readonly integrations = this._integrations.asReadonly()
  readonly loadingIntegrations = this._loadingIntegrations.asReadonly()
  readonly busyIntegrationId = this._busyIntegrationId.asReadonly()

  readonly jira = computed(() => this._integrations().find((item) => item.id === 'jira'))
  readonly github = computed(() => this._integrations().find((item) => item.id === 'github'))
  readonly gitlab = computed(() => this._integrations().find((item) => item.id === 'gitlab'))

  readonly connectedCount = computed(() => this._integrations().filter((i) => i.status === 'connected').length)

  constructor() {
    // useEffect(() => { if (!isEnabled) return; loadIntegrations() }, [loadIntegrations, isEnabled])
    effect(() => {
      if (!this.isEnabled()) return
      untracked(() => void this.loadIntegrations())
    })

    // OAuth callbacks listener — re-runs whenever the query string changes (React deps: [searchParams]).
    effect(() => {
      const searchParams = this.currentUrl.searchParams()
      untracked(() => {
        if (!this.isEnabled()) return
        this.handleCallback(searchParams, 'jira', 'Jira')
        this.handleCallback(searchParams, 'github', 'GitHub')
        this.handleCallback(searchParams, 'gitlab', 'GitLab')
      })
    })
  }

  /** Equivalent of the hook's `options` argument. */
  configure(options?: IntegrationsManagerOptions): void {
    const enabled = options?.enabled
    if (typeof enabled === 'function') {
      this.enabledSource.set(enabled)
    } else {
      const value = enabled ?? true
      this.enabledSource.set(() => value)
    }
  }

  setEnabled(enabled: boolean): void {
    this.configure({ enabled })
  }

  async loadIntegrations(): Promise<void> {
    this._loadingIntegrations.set(true)
    try {
      const items = await api.getIntegrations()
      this._integrations.set(items)
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Error al cargar las integraciones'
      this.toastService.toast.error(errMsg)
    } finally {
      this._loadingIntegrations.set(false)
    }
  }

  async handlePatConnected(id: string, label: string): Promise<void> {
    try {
      await api.syncIntegration(id)
      this.toastService.toast.success(`${label} conectado. Datos sincronizados.`)
    } catch {
      this.toastService.toast.success(`${label} conectado. Selecciona proyectos o repositorios para sincronizar.`)
    }
    await this.loadIntegrations()
  }

  async handleOAuthConnect(id: string): Promise<void> {
    this._busyIntegrationId.set(id)
    try {
      const result = await api.startOAuth(id)
      window.location.href = result.authorization_url
    } catch (err) {
      this.toastService.toast.error(err instanceof Error ? err.message : 'No se pudo iniciar el flujo OAuth')
      this._busyIntegrationId.set(null)
    }
  }

  async handleDisconnect(id: string): Promise<void> {
    this._busyIntegrationId.set(id)
    try {
      await api.disconnectIntegration(id)
      this.toastService.toast.info(`${id.toUpperCase()} desconectado. Credenciales locales eliminadas.`)
      await this.loadIntegrations()
    } catch (err) {
      this.toastService.toast.error(err instanceof Error ? err.message : 'Error al desconectar integración')
    } finally {
      this._busyIntegrationId.set(null)
    }
  }

  async handleTest(id: string): Promise<void> {
    this._busyIntegrationId.set(id)
    try {
      const result = await api.testIntegration(id)
      if (result.ok) {
        this.toastService.toast.success(result.message)
      } else {
        this.toastService.toast.error(result.message)
      }
    } catch (err) {
      this.toastService.toast.error(err instanceof Error ? err.message : 'Error al verificar la conexión')
    } finally {
      this._busyIntegrationId.set(null)
    }
  }

  private handleCallback(searchParams: URLSearchParams, key: 'jira' | 'github' | 'gitlab', label: string): void {
    const status = searchParams.get(key)
    const rawMessage = searchParams.get('message')
    if (status === 'connected') {
      this.toastService.toast.success(`${label} conectado exitosamente. Datos en vivo sincronizados.`)
      this.replaceSearchParams({ tab: 'integrations' })
      void this.loadIntegrations()
    } else if (status === 'error') {
      const decoded = rawMessage ? decodeURIComponent(rawMessage) : `Error en OAuth de ${label}.`
      const err =
        key === 'jira'
          ? `${decoded} Si Atlassian mostró "Something went wrong" al aceptar, verifica los permisos en la consola de desarrollador de Atlassian o conéctate con Personal Access Token.`
          : decoded
      this.toastService.toast.error(err)
      this.replaceSearchParams({ tab: 'integrations' })
    }
  }

  /** `setSearchParams(params, { replace: true })`: replaces the whole query string, keeps the path. */
  private replaceSearchParams(params: Record<string, string>): void {
    const tree = this.router.parseUrl(this.router.url)
    tree.queryParams = params
    tree.fragment = null
    void this.router.navigateByUrl(tree, { replaceUrl: true })
  }
}

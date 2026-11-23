import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core'
import { api, type AuthUser } from '../../../api/client'
import { ToastService } from '../../../core/notifications/toast.service'

export type UserApprovalsManagerOptions = {
  /** Same as the React hook option. Accepts a plain boolean or a reactive getter (e.g. a signal/computed). */
  enabled?: boolean | (() => boolean)
}

/**
 * Angular port of React `useUserApprovalsManager(options?)`.
 *
 * `@Injectable()` without `providedIn`: list it in the consuming component's `providers`
 * (one instance per component, like a hook call).
 *
 * Hook option → `configure({ enabled })` (boolean or signal/getter). Call it from the consumer's
 * constructor / field initializer so the first load already honours it. `setEnabled(bool)` is a shortcut.
 * Default: enabled = true (same as the hook).
 *
 * Public members (same names as the hook's return object):
 * - State (signals, read with `()`): `pendingRequests`, `loadingRequests`
 * - Methods: `loadAccessRequests()`, `handleApproveRequest(userId, uname)`, `handleRejectRequest(userId, uname)`
 *
 * Side effect (same as the hook): loads the access requests whenever it becomes enabled.
 */
@Injectable()
export class UserApprovalsManagerService {
  private readonly toastService = inject(ToastService)

  private readonly _pendingRequests = signal<AuthUser[]>([])
  private readonly _loadingRequests = signal(false)
  private readonly enabledSource = signal<() => boolean>(() => true)
  private readonly isEnabled = computed(() => this.enabledSource()())

  readonly pendingRequests = this._pendingRequests.asReadonly()
  readonly loadingRequests = this._loadingRequests.asReadonly()

  constructor() {
    effect(() => {
      if (!this.isEnabled()) return
      untracked(() => void this.loadAccessRequests())
    })
  }

  /** Equivalent of the hook's `options` argument. */
  configure(options?: UserApprovalsManagerOptions): void {
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

  async loadAccessRequests(): Promise<void> {
    this._loadingRequests.set(true)
    try {
      const res = await api.getAccessRequests()
      this._pendingRequests.set(res.requests || [])
    } catch {
      // ignore
    } finally {
      this._loadingRequests.set(false)
    }
  }

  async handleApproveRequest(userId: string, uname: string): Promise<void> {
    try {
      await api.approveAccessRequest(userId)
      this.toastService.toast.success(`Acceso aprobado con éxito para el usuario '${uname}'.`, 'Aprobado')
      void this.loadAccessRequests()
    } catch (err) {
      this.toastService.toast.error(
        err instanceof Error ? err.message : 'Error al aprobar la solicitud de acceso',
        'Error',
      )
    }
  }

  async handleRejectRequest(userId: string, uname: string): Promise<void> {
    try {
      await api.rejectAccessRequest(userId)
      this.toastService.toast.info(`Solicitud rechazada para el usuario '${uname}'.`, 'Rechazado')
      void this.loadAccessRequests()
    } catch (err) {
      this.toastService.toast.error(
        err instanceof Error ? err.message : 'Error al rechazar la solicitud de acceso',
        'Error',
      )
    }
  }
}

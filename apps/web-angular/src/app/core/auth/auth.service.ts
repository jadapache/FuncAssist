import { Injectable, computed, inject, signal } from '@angular/core'
import { Router } from '@angular/router'
import { api, type AuthUser } from '../../api/client'
import { AUTH_TOKEN_KEY } from '../../constants/app'

export type RegisterResult = { status?: string; message?: string; token?: string; user?: AuthUser }

/**
 * Session state for the whole app (Angular port of React `AuthContext`).
 *
 * - Same localStorage key as the React frontend, so sessions survive the switch.
 * - `isLoading` starts true and flips false once the stored token was validated against `/api/auth/me`.
 * - `whenReady()` lets route guards wait for that validation (React rendered a spinner instead).
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly router = inject(Router)

  readonly user = signal<AuthUser | null>(null)
  readonly token = signal<string | null>(readStoredToken())
  readonly isLoading = signal(true)
  readonly error = signal<string | null>(null)
  readonly isAuthenticated = computed(() => !!this.user() && !!this.token())

  private readonly ready: Promise<void>

  constructor() {
    this.ready = this.initAuth()
  }

  /** Resolves once the initial session check has finished. */
  whenReady(): Promise<void> {
    return this.ready
  }

  private async initAuth(): Promise<void> {
    const storedToken = readStoredToken()
    if (!storedToken) {
      this.isLoading.set(false)
      return
    }
    try {
      const res = await api.getMe()
      this.user.set(res.user)
      this.token.set(storedToken)
    } catch {
      localStorage.removeItem(AUTH_TOKEN_KEY)
      this.token.set(null)
      this.user.set(null)
    } finally {
      this.isLoading.set(false)
    }
  }

  async login(username: string, password: string): Promise<void> {
    this.isLoading.set(true)
    this.error.set(null)
    try {
      const res = await api.login({ username, password })
      if (res.token) {
        localStorage.setItem(AUTH_TOKEN_KEY, res.token)
        this.token.set(res.token)
        this.user.set(res.user)
      }
    } catch (err: unknown) {
      this.error.set(err instanceof Error ? err.message : 'Error al iniciar sesión')
      throw err
    } finally {
      this.isLoading.set(false)
    }
  }

  async register(
    username: string,
    password: string,
    email?: string,
    fullName?: string,
    role?: string,
  ): Promise<RegisterResult> {
    this.isLoading.set(true)
    this.error.set(null)
    try {
      const res = await api.register({
        username,
        password,
        email,
        full_name: fullName,
        role: role || 'user',
      })
      if (res.token && res.user) {
        localStorage.setItem(AUTH_TOKEN_KEY, res.token)
        this.token.set(res.token)
        this.user.set(res.user)
      }
      return res
    } catch (err: unknown) {
      this.error.set(err instanceof Error ? err.message : 'Error al solicitar acceso')
      throw err
    } finally {
      this.isLoading.set(false)
    }
  }

  /** Clears the session. React's ProtectedRoute redirected reactively; Angular navigates explicitly. */
  logout(): void {
    localStorage.removeItem(AUTH_TOKEN_KEY)
    this.token.set(null)
    this.user.set(null)
    void this.router.navigateByUrl('/login', { replaceUrl: true })
  }

  clearError(): void {
    this.error.set(null)
  }

  updateUser(newUser: AuthUser): void {
    this.user.set(newUser)
  }
}

function readStoredToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY)
  } catch {
    return null
  }
}

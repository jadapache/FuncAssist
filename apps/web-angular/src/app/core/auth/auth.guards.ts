import { inject } from '@angular/core'
import { Router, type CanActivateFn } from '@angular/router'
import type { UserRole } from '../../api/client'
import { AuthService } from './auth.service'

/** Port of React `<ProtectedRoute />`: waits for the session check, then requires a user. */
export const authGuard: CanActivateFn = async () => {
  const auth = inject(AuthService)
  const router = inject(Router)
  await auth.whenReady()
  if (!auth.isAuthenticated() || !auth.user()) {
    return router.parseUrl('/login')
  }
  return true
}

/** Port of React `<ProtectedRoute allowedRoles={...} />`: unauthorized roles go back to `/`. */
export const roleGuard =
  (allowedRoles: UserRole[]): CanActivateFn =>
  async () => {
    const auth = inject(AuthService)
    const router = inject(Router)
    await auth.whenReady()
    const user = auth.user()
    if (!auth.isAuthenticated() || !user) {
      return router.parseUrl('/login')
    }
    const userRole = (user.role as UserRole) || 'funcional'
    if (!allowedRoles.includes(userRole)) {
      return router.parseUrl('/')
    }
    return true
  }

import { Injectable, computed, inject } from '@angular/core'
import { api, type UserProfile, type UserRole } from '../../api/client'
import { AuthService } from './auth.service'

export type { UserRole, UserProfile }

/** Angular port of React `UserContext`: a profile view derived from the authenticated user. */
@Injectable({ providedIn: 'root' })
export class UserService {
  private readonly auth = inject(AuthService)

  readonly user = computed<UserProfile | null>(() => {
    const authUser = this.auth.user()
    return authUser
      ? {
          display_name: authUser.full_name || authUser.username,
          user_role: (authUser.role as UserRole) || 'funcional',
        }
      : null
  })

  readonly isLoading = this.auth.isLoading
  readonly isFirstTimeSetup = false

  async updateProfile(updates: Partial<UserProfile>): Promise<void> {
    if (!this.auth.user()) return
    const res = await api.updateProfile({ full_name: updates.display_name })
    this.auth.updateUser(res.user)
  }

  /** Kept for backward compatibility with the React API surface. */
  async completeSetup(_profile: UserProfile): Promise<void> {}
}

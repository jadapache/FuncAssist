import { API_BASE, getAuthHeaders, handleResponse } from '../client'

export type UserRole = 'admin' | 'pm' | 'funcional' | 'qa'

export interface UserProfile {
  display_name: string
  user_role: UserRole
  documents_path?: string
}

export const userApi = {
  getUserProfile: async (): Promise<UserProfile> => {
    const res = await fetch(`${API_BASE}/api/user/profile`, {
      headers: { ...getAuthHeaders() },
    })
    return handleResponse<UserProfile>(res)
  },

  updateUserProfile: async (updates: Partial<UserProfile>): Promise<UserProfile> => {
    const res = await fetch(`${API_BASE}/api/user/profile`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(updates),
    })
    return handleResponse<UserProfile>(res)
  },

  setupUser: async (profile: UserProfile): Promise<UserProfile> => {
    const res = await fetch(`${API_BASE}/api/user/setup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(profile),
    })
    return handleResponse<UserProfile>(res)
  },
}

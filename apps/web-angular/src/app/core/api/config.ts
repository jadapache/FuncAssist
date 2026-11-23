import { AUTH_TOKEN_KEY } from '../../constants/app'
import { environment } from '../../../environments/environment'

export const API_BASE: string = environment.apiBase

export const getAuthToken = (): string | null => {
  return localStorage.getItem(AUTH_TOKEN_KEY)
}

export const getAuthHeaders = (): Record<string, string> => {
  const token = getAuthToken()

  return token ? { Authorization: `Bearer ${token}` } : {}
}

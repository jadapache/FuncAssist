import { AUTH_TOKEN_KEY } from '../../constants/app'

export const API_BASE =
  import.meta.env.VITE_API_BASE || 'http://127.0.0.1:6728'

export const getAuthHeaders = (): Record<string, string> => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)

  return token ? { Authorization: `Bearer ${token}` } : {}
}
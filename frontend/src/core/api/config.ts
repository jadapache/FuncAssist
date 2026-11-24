export const API_BASE =
  import.meta.env.VITE_API_BASE !== undefined ? import.meta.env.VITE_API_BASE : ''

/**
 * Session JWT lives in an HttpOnly cookie set by the backend; JavaScript never reads
 * it. Same-origin requests (Nginx in production, the Vite proxy in development) send it.
 */
export const getAuthHeaders = (): Record<string, string> => ({})

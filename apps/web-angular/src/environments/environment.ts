/**
 * Production environment.
 * `apiBase` empty = same-origin requests (nginx proxies /api/ to the backend),
 * exactly like the React build when VITE_API_BASE is unset.
 */
export const environment = {
  production: true,
  apiBase: '',
  authTokenKey: 'funcassist_auth_token',
}

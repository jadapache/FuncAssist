/**
 * Development environment.
 * `apiBase` stays empty: `ng serve` proxies /api to http://127.0.0.1:6728 (see proxy.conf.json),
 * which avoids CORS since the backend allowlist only includes the React/Vite origins.
 */
export const environment = {
  production: false,
  apiBase: '',
  authTokenKey: 'funcassist_auth_token',
}

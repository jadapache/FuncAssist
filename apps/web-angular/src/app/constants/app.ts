import { environment } from '../../environments/environment'

export const DEFAULT_DISPLAY_NAME = 'PM'

export const toolsGroupLabel = (displayName: string) => `Herramientas ${displayName || DEFAULT_DISPLAY_NAME}`

/** Same key as the React app so existing sessions survive the frontend switch. */
export const AUTH_TOKEN_KEY = environment.authTokenKey ?? 'funcassist_auth_token'

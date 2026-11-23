import { API_BASE, getAuthHeaders, handleResponse, type AuthUser, type AuthResponse } from '../client'

export const authApi = {
  register: (payload: { username: string; password: string; email?: string; full_name?: string; role?: string }) =>
    fetch(`${API_BASE}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<AuthResponse>(r)),

  login: (payload: { username: string; password: string }) =>
    fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<AuthResponse>(r)),

  getMe: () =>
    fetch(`${API_BASE}/api/auth/me`, {
      method: 'GET',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ user: AuthUser }>(r)),

  updateProfile: (payload: { full_name?: string; email?: string; password?: string }) =>
    fetch(`${API_BASE}/api/auth/me`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<{ message: string; user: AuthUser }>(r)),

  getAccessRequests: () =>
    fetch(`${API_BASE}/api/auth/access-requests`, {
      method: 'GET',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ requests: AuthUser[] }>(r)),

  approveAccessRequest: (userId: string) =>
    fetch(`${API_BASE}/api/auth/access-requests/${userId}/approve`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ status: string; user: AuthUser }>(r)),

  rejectAccessRequest: (userId: string) =>
    fetch(`${API_BASE}/api/auth/access-requests/${userId}/reject`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
    }).then((r) => handleResponse<{ status: string; user: AuthUser }>(r)),
}

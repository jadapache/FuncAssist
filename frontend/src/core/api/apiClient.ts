/**
 * apiClient.ts
 * Base API Client with standardized error handling and request methods
 */

import { API_BASE, getAuthHeaders } from '../../api/client'
 
export interface ApiClientConfig {
  baseUrl?: string
}

export class ApiError extends Error {
  public status: number
  public data: any

  constructor(message: string, status: number, data?: any) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

export class ApiClient {
  private baseUrl: string

  constructor(config?: ApiClientConfig) {
    this.baseUrl = config?.baseUrl ?? API_BASE
  }

  private getAuthHeader(): Record<string, string> {
    return getAuthHeaders()
  }

  private async handleResponse<T>(res: Response): Promise<T> {
    if (!res.ok) {
      let errorData: any
      try {
        errorData = await res.json()
      } catch {
        errorData = await res.text()
      }
      const message =
        typeof errorData === 'object' && errorData?.detail
          ? typeof errorData.detail === 'string'
            ? errorData.detail
            : JSON.stringify(errorData.detail)
          : res.statusText || 'Error en la petición al servidor'
      throw new ApiError(message, res.status, errorData)
    }
    return res.json() as Promise<T>
  }

  public async get<T>(url: string, headers?: Record<string, string>): Promise<T> {
    const res = await fetch(`${this.baseUrl}${url}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...this.getAuthHeader(),
        ...headers,
      },
    })
    return this.handleResponse<T>(res)
  }

  public async post<T>(url: string, body?: any, headers?: Record<string, string>): Promise<T> {
    const res = await fetch(`${this.baseUrl}${url}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...this.getAuthHeader(),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    return this.handleResponse<T>(res)
  }

  public async put<T>(url: string, body?: any, headers?: Record<string, string>): Promise<T> {
    const res = await fetch(`${this.baseUrl}${url}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...this.getAuthHeader(),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    return this.handleResponse<T>(res)
  }

  public async delete<T>(url: string, headers?: Record<string, string>): Promise<T> {
    const res = await fetch(`${this.baseUrl}${url}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        ...this.getAuthHeader(),
        ...headers,
      },
    })
    return this.handleResponse<T>(res)
  }

  public async uploadFile<T>(url: string, formData: FormData, headers?: Record<string, string>): Promise<T> {
    const res = await fetch(`${this.baseUrl}${url}`, {
      method: 'POST',
      headers: {
        ...this.getAuthHeader(),
        ...headers,
      },
      body: formData,
    })
    return this.handleResponse<T>(res)
  }
}

export const apiClient = new ApiClient()


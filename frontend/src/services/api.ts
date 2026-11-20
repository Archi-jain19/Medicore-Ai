import axios, { AxiosError } from 'axios'

export const TOKEN_KEY = 'medicore.token'

export const api = axios.create({
  // Same-origin '/api' by default (Vite proxy in dev, nginx in production). Set VITE_API_BASE_URL only when
  // the API is deployed on a different origin (e.g. Vercel + Render).
  baseURL: `${(import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')}/api`,
  timeout: 60_000,
})

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

api.interceptors.request.use((config) => {
  const token = readToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

api.interceptors.response.use(
  (r) => r,
  (error: AxiosError) => {
    const url = error.config?.url ?? ''
    if (error.response?.status === 401 && !url.startsWith('/auth/')) onUnauthorized?.()
    return Promise.reject(error)
  },
)

interface ApiErrorBody {
  error?: { code?: string; message?: string; details?: { field: string; message: string }[] }
}

/** Human-readable message from the backend's error envelope. */
export function errorMessage(err: unknown, fallback = 'Something went wrong. Please try again in a moment.'): string {
  if (axios.isAxiosError(err)) {
    if (err.code === 'ECONNABORTED') return 'That is taking longer than expected. Please try again.'
    if (!err.response) return 'We cannot connect right now. Please check your internet connection and try again.'
    const body = err.response.data as ApiErrorBody | undefined
    // Field-level technical messages (e.g. "String should have at least 8 characters") are not useful to people
    if (body?.error?.details?.length) return 'Some of the information you entered is not valid. Please check it and try again.'
    if (body?.error?.message) return body.error.message
    if (err.response.status === 429) return 'Too many requests. Please wait a moment and try again.'
    if (err.response.status >= 500) return 'Something went wrong on our side. Please try again in a moment.'
  }
  return fallback
}

export function errorCode(err: unknown): string | undefined {
  if (axios.isAxiosError(err)) return (err.response?.data as ApiErrorBody | undefined)?.error?.code
  return undefined
}

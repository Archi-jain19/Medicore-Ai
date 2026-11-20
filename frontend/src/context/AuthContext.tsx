import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setUnauthorizedHandler, TOKEN_KEY } from '@/services/api'
import type { TokenResponse, User } from '@/types/api'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName?: string) => Promise<void>
  logout: () => void
  /** Replace the session token (e.g. after a password change revokes the old one). */
  setToken: (token: string) => void
  refresh: () => Promise<void>
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthState | null>(null)

function storeToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable — session lasts for this tab only */
  }
}

function hasToken() {
  try {
    return !!localStorage.getItem(TOKEN_KEY)
  } catch {
    return false
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const logout = useCallback(() => {
    storeToken(null)
    setUser(null)
  }, [])

  const refresh = useCallback(async () => {
    if (!hasToken()) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      const { data } = await api.get<User>('/auth/me')
      setUser(data)
    } catch {
      storeToken(null)
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(logout)
    void refresh()
  }, [logout, refresh])

  const login = useCallback(
    async (email: string, password: string) => {
      const { data } = await api.post<TokenResponse>('/auth/login', { email, password })
      storeToken(data.access_token)
      await refresh()
    },
    [refresh],
  )

  const register = useCallback(
    async (email: string, password: string, fullName?: string) => {
      const { data } = await api.post<TokenResponse>('/auth/register', {
        email,
        password,
        full_name: fullName || null,
      })
      storeToken(data.access_token)
      await refresh()
    },
    [refresh],
  )

  const setToken = useCallback((token: string) => storeToken(token), [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout, refresh, setToken }),
    [user, loading, login, register, logout, refresh, setToken],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

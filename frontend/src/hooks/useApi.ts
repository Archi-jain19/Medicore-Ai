import { useCallback, useEffect, useState } from 'react'
import { api, errorCode, errorMessage } from '@/services/api'

/** GET a resource with loading / error state. Re-fetch with `reload()`. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [code, setCode] = useState<string | undefined>()
  const [loading, setLoading] = useState(!!path)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (!path) return
    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .get<T>(path)
      .then((r) => !cancelled && setData(r.data))
      .catch((e) => {
        if (cancelled) return
        setError(errorMessage(e))
        setCode(errorCode(e))
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [path, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { data, error, code, loading, reload }
}

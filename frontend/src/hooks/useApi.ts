import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../lib/api'

export interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  reload: () => void
}

/**
 * Runs a fetcher on mount and whenever `deps` change.
 * Stale responses are discarded so rapid filter changes cannot race.
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)
  const requestId = useRef(0)

  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  useEffect(() => {
    const id = ++requestId.current
    let cancelled = false
    setLoading(true)
    setError(null)

    fetcherRef
      .current()
      .then((result) => {
        if (cancelled || id !== requestId.current) return
        setData(result)
      })
      .catch((caught: unknown) => {
        if (cancelled || id !== requestId.current) return
        setError(
          caught instanceof ApiError
            ? caught.message
            : 'Something went wrong loading this view.',
        )
      })
      .finally(() => {
        if (cancelled || id !== requestId.current) return
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { data, loading, error, reload }
}

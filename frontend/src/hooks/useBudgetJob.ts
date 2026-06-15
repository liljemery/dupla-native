import { useCallback, useEffect, useRef, useState } from 'react'
import { enqueueBudgetJob, getBudgetResult, getLatestBudgetJob } from '../api/budget'
import type { BudgetJob, BudgetResult } from '../types/budget'

const POLL_INTERVAL_MS = 5000
const ACTIVE_STATUSES = new Set(['queued', 'processing'])

interface UseBudgetJobReturn {
  job: BudgetJob | null
  result: BudgetResult | null
  isPolling: boolean
  error: string | null
  enqueue: (opts?: { discipline?: string }) => Promise<void>
  refresh: () => void
}

export function useBudgetJob(projectUuid: string, token: string | null): UseBudgetJobReturn {
  const [job, setJob] = useState<BudgetJob | null>(null)
  const [result, setResult] = useState<BudgetResult | null>(null)
  const [isPolling, setIsPolling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const mountedRef = useRef(true)

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    setIsPolling(false)
  }, [])

  const fetchResult = useCallback(async () => {
    const r = await getBudgetResult(projectUuid, token)
    if (mountedRef.current) setResult(r)
  }, [projectUuid, token])

  const pollOnce = useCallback(async () => {
    const latest = await getLatestBudgetJob(projectUuid, token)
    if (!mountedRef.current) return
    if (!latest) return
    setJob(latest)
    if (latest.status === 'completed') {
      stopPolling()
      await fetchResult()
    } else if (latest.status === 'failed') {
      stopPolling()
      setError(latest.error ?? 'El procesamiento falló')
    }
  }, [projectUuid, token, stopPolling, fetchResult])

  const startPolling = useCallback(() => {
    if (intervalRef.current) return
    setIsPolling(true)
    intervalRef.current = setInterval(() => {
      void pollOnce()
    }, POLL_INTERVAL_MS)
  }, [pollOnce])

  // Initial fetch
  useEffect(() => {
    mountedRef.current = true
    void (async () => {
      const latest = await getLatestBudgetJob(projectUuid, token)
      if (!mountedRef.current) return
      if (!latest) return
      setJob(latest)
      if (ACTIVE_STATUSES.has(latest.status)) {
        startPolling()
      } else if (latest.status === 'completed') {
        await fetchResult()
      } else if (latest.status === 'failed') {
        setError(latest.error ?? 'El procesamiento falló')
      }
    })()
    return () => {
      mountedRef.current = false
      stopPolling()
    }
  }, [projectUuid, token, startPolling, stopPolling, fetchResult])

  const enqueue = useCallback(
    async (opts?: { discipline?: string }) => {
      setError(null)
      try {
        const newJob = await enqueueBudgetJob(projectUuid, token, opts)
        if (!mountedRef.current) return
        setJob(newJob)
        setResult(null)
        startPolling()
      } catch (e) {
        if (!mountedRef.current) return
        setError(e instanceof Error ? e.message : 'Error al encolar')
      }
    },
    [projectUuid, token, startPolling],
  )

  const refresh = useCallback(() => {
    void pollOnce()
  }, [pollOnce])

  return { job, result, isPolling, error, enqueue, refresh }
}

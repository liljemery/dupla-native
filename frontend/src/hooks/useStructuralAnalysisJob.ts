import { useCallback, useEffect, useRef, useState } from 'react'
import {
  enqueueClashJob,
  getLatestClashJob,
  getStructuralAnalysisReport,
} from '../api/structuralAnalysis'
import type { ClashJob } from '../types/clashJob'
import type { StructuralAnalysisReport } from '../types/structuralAnalysisReport'

const POLL_INTERVAL_MS = 5000
const ACTIVE_STATUSES = new Set(['queued', 'processing'])

const EMPTY_REPORT: StructuralAnalysisReport = {
  run_status: 'pending',
  title: 'Informe de coordinación',
  subtitle: 'Selecciona la carpeta con planos etiquetados por disciplina y ejecuta el análisis.',
  summary: { errors: 0, warnings: 0, ok: 0 },
  clashes: [],
  clash_relationships: [],
  analyzed_documents: [],
  ai_insight: 'Aún no hay una corrida de análisis completada para este proyecto.',
  zoning_rows: [],
  footer_status_message: 'Pendiente de análisis',
}

interface UseStructuralAnalysisJobReturn {
  job: ClashJob | null
  report: StructuralAnalysisReport
  isPolling: boolean
  error: string | null
  enqueue: (opts?: { folder_uuid?: string }) => Promise<void>
  refresh: () => void
}

export function useStructuralAnalysisJob(
  projectUuid: string,
  token: string | null,
): UseStructuralAnalysisJobReturn {
  const [job, setJob] = useState<ClashJob | null>(null)
  const [report, setReport] = useState<StructuralAnalysisReport>(EMPTY_REPORT)
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

  const fetchReport = useCallback(async () => {
    const r = await getStructuralAnalysisReport(projectUuid, token)
    if (!mountedRef.current) return
    if (r) setReport(r)
  }, [projectUuid, token])

  const pollOnce = useCallback(async () => {
    const latest = await getLatestClashJob(projectUuid, token)
    if (!mountedRef.current) return
    if (!latest) return
    setJob(latest)
    await fetchReport()
    if (latest.status === 'completed') {
      stopPolling()
    } else if (latest.status === 'failed') {
      stopPolling()
      setError(latest.error ?? 'El análisis de clashes falló')
    }
  }, [projectUuid, token, stopPolling, fetchReport])

  const startPolling = useCallback(() => {
    if (intervalRef.current) return
    setIsPolling(true)
    void pollOnce()
    intervalRef.current = setInterval(() => {
      void pollOnce()
    }, POLL_INTERVAL_MS)
  }, [pollOnce])

  useEffect(() => {
    mountedRef.current = true
    void (async () => {
      const latest = await getLatestClashJob(projectUuid, token)
      if (!mountedRef.current) return
      if (latest) {
        setJob(latest)
        await fetchReport()
        if (ACTIVE_STATUSES.has(latest.status)) {
          startPolling()
        } else if (latest.status === 'failed') {
          setError(latest.error ?? 'El análisis de clashes falló')
        }
      } else {
        await fetchReport()
      }
    })()
    return () => {
      mountedRef.current = false
      stopPolling()
    }
  }, [projectUuid, token, startPolling, stopPolling, fetchReport])

  const enqueue = useCallback(
    async (opts?: { folder_uuid?: string }) => {
      setError(null)
      try {
        const newJob = await enqueueClashJob(projectUuid, token, opts)
        if (!mountedRef.current) return
        setJob(newJob)
        setReport((prev) => ({ ...prev, run_status: 'running', footer_status_message: 'Análisis en curso…' }))
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

  return { job, report, isPolling, error, enqueue, refresh }
}

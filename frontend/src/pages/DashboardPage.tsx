import { useEffect, useState } from 'react'

import { apiFetch } from '../api/client'
import { Card } from '../components/Card'
import { WORKFLOW_PHASE_LABELS, WORKFLOW_PHASE_ORDER } from '../constants/workflowPhases'
import { useAuthStore } from '../store/authStore'

type Summary = {
  projects_by_phase: Record<string, number>
  pending_task_cards: number
  projects_past_deadline: number
}

export function DashboardPage() {
  const token = useAuthStore((s) => s.token)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    void (async () => {
      setErr(null)
      const res = await apiFetch('/api/dashboard/summary', { token })
      if (!res.ok) {
        if (!cancelled) setErr('No se pudieron cargar los indicadores')
        return
      }
      const body = (await res.json()) as Summary
      if (!cancelled) setSummary(body)
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  const phaseEntries = summary
    ? Object.entries(summary.projects_by_phase).sort(([a], [b]) => {
        const ia = WORKFLOW_PHASE_ORDER.indexOf(a as (typeof WORKFLOW_PHASE_ORDER)[number])
        const ib = WORKFLOW_PHASE_ORDER.indexOf(b as (typeof WORKFLOW_PHASE_ORDER)[number])
        const sa = ia >= 0 ? ia : 999
        const sb = ib >= 0 ? ib : 999
        return sa - sb || a.localeCompare(b)
      })
    : []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-ink">Panel gerencial</h1>
        <p className="mt-1 text-sm text-muted">
          Vista consolidada para Gerencia. Datos en tiempo casi real desde la API.
        </p>
      </div>
      {err ? <p className="text-sm text-primary">{err}</p> : null}
      {!summary && !err ? <p className="text-sm text-muted">Cargando…</p> : null}
      {summary ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Card className="p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">Tareas Kanban pendientes</p>
            <p className="mt-2 text-3xl font-bold tabular-nums text-ink">{summary.pending_task_cards}</p>
            <p className="mt-1 text-xs text-muted">Tarjetas fuera de la columna «Completado»</p>
          </Card>
          <Card className="p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">Proyectos con plazo vencido</p>
            <p className="mt-2 text-3xl font-bold tabular-nums text-primary">{summary.projects_past_deadline}</p>
            <p className="mt-1 text-xs text-muted">Con fecha límite anterior a hoy y no en COMPLETE</p>
          </Card>
          <Card className="p-5 sm:col-span-2 lg:col-span-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">Total proyectos listados</p>
            <p className="mt-2 text-3xl font-bold tabular-nums text-ink">
              {Object.values(summary.projects_by_phase).reduce((a, b) => a + b, 0)}
            </p>
          </Card>
        </div>
      ) : null}
      {summary ? (
        <Card className="p-5">
          <h2 className="text-sm font-semibold text-ink">Proyectos por fase</h2>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {phaseEntries.length === 0 ? (
              <li className="text-sm text-muted">Sin proyectos.</li>
            ) : (
              phaseEntries.map(([phase, count]) => (
                <li key={phase} className="flex justify-between gap-4 rounded border border-black/5 px-3 py-2 text-sm">
                  <span className="text-ink">{WORKFLOW_PHASE_LABELS[phase] ?? phase}</span>
                  <span className="tabular-nums font-medium text-ink">{count}</span>
                </li>
              ))
            )}
          </ul>
        </Card>
      ) : null}
    </div>
  )
}

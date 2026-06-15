import { apiFetch } from './client'
import type { BudgetJob, BudgetResult } from '../types/budget'

export async function enqueueBudgetJob(
  projectUuid: string,
  token: string | null,
  opts?: { discipline?: string },
): Promise<BudgetJob> {
  const res = await apiFetch(`/api/projects/${projectUuid}/budget/jobs`, {
    method: 'POST',
    token,
    body: JSON.stringify({
      discipline: opts?.discipline ?? null,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'Error al encolar el presupuesto')
  }
  return (await res.json()) as BudgetJob
}

export async function getLatestBudgetJob(
  projectUuid: string,
  token: string | null,
): Promise<BudgetJob | null> {
  const res = await apiFetch(`/api/projects/${projectUuid}/budget/jobs/latest`, { token })
  if (res.status === 404) return null
  if (!res.ok) return null
  return (await res.json()) as BudgetJob
}

export async function getBudgetResult(
  projectUuid: string,
  token: string | null,
): Promise<BudgetResult | null> {
  const res = await apiFetch(`/api/projects/${projectUuid}/budget/result`, { token })
  if (res.status === 404) return null
  if (!res.ok) return null
  return (await res.json()) as BudgetResult
}

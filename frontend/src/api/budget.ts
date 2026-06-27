import { apiFetch } from './client'
import type { BudgetJob, BudgetResult } from '../types/budget'

function parseApiDetail(body: unknown): string | null {
  if (!body || typeof body !== 'object' || !('detail' in body)) return null
  const detail = (body as { detail: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg)
        }
        return null
      })
      .filter((part): part is string => Boolean(part))
    return parts.length > 0 ? parts.join('; ') : null
  }
  return null
}

function normalizeBudgetDisciplineForApi(discipline?: string): string | null {
  const value = (discipline ?? '').trim().toLowerCase()
  if (!value || value === 'todas') return null
  return discipline!.trim()
}

export async function enqueueBudgetJob(
  projectUuid: string,
  token: string | null,
  opts?: { discipline?: string },
): Promise<BudgetJob> {
  const res = await apiFetch(`/api/projects/${projectUuid}/budget/jobs`, {
    method: 'POST',
    token,
    silent: true,
    body: JSON.stringify({
      discipline: normalizeBudgetDisciplineForApi(opts?.discipline),
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(parseApiDetail(err) ?? 'Error al encolar el presupuesto')
  }
  return (await res.json()) as BudgetJob
}

export async function getLatestBudgetJob(
  projectUuid: string,
  token: string | null,
): Promise<BudgetJob | null> {
  const res = await apiFetch(`/api/projects/${projectUuid}/budget/jobs/latest`, {
    token,
    silent: true,
  })
  if (res.status === 404) return null
  if (!res.ok) return null
  const body = (await res.json()) as BudgetJob | null
  return body ?? null
}

export async function getBudgetResult(
  projectUuid: string,
  token: string | null,
): Promise<BudgetResult | null> {
  const res = await apiFetch(`/api/projects/${projectUuid}/budget/result`, {
    token,
    silent: true,
  })
  if (res.status === 404) return null
  if (!res.ok) return null
  return (await res.json()) as BudgetResult
}

export async function saveBudgetResult(
  projectUuid: string,
  token: string | null,
  rows: BudgetResult['rows'],
): Promise<BudgetResult> {
  const res = await apiFetch(`/api/projects/${projectUuid}/budget/result`, {
    method: 'PATCH',
    token,
    body: JSON.stringify({ rows }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(parseApiDetail(err) ?? 'Error al guardar presupuesto')
  }
  return (await res.json()) as BudgetResult
}

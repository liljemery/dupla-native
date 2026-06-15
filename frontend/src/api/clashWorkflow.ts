import { apiFetch } from './client'
import { downloadBlob, filenameFromContentDisposition } from '../lib/download'
import type {
  ClashDetail,
  ClashFilters,
  ClashRow,
  CorrectionResult,
  CorrectionTarget,
  DashboardMetrics,
  FilterOptions,
  ReviewerDecision,
  ClashStatus,
} from '../types/clashWorkflow'

function qs(filters: ClashFilters): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v) params.set(k, v)
  }
  const s = params.toString()
  return s ? `?${s}` : ''
}

export async function getClashWorkflowDashboard(
  projectUuid: string,
  token: string | null,
  filters: ClashFilters = {},
): Promise<DashboardMetrics | null> {
  const res = await apiFetch(`/api/projects/${projectUuid}/clash-workflow/dashboard${qs(filters)}`, { token })
  if (!res.ok) return null
  return (await res.json()) as DashboardMetrics
}

export async function getClashWorkflowFilters(
  projectUuid: string,
  token: string | null,
): Promise<FilterOptions | null> {
  const res = await apiFetch(`/api/projects/${projectUuid}/clash-workflow/filters`, { token })
  if (!res.ok) return null
  return (await res.json()) as FilterOptions
}

export async function listClashWorkflowRows(
  projectUuid: string,
  token: string | null,
  filters: ClashFilters = {},
): Promise<ClashRow[]> {
  const res = await apiFetch(`/api/projects/${projectUuid}/clash-workflow/clashes${qs(filters)}`, { token })
  if (!res.ok) return []
  return (await res.json()) as ClashRow[]
}

export async function getClashWorkflowDetail(
  projectUuid: string,
  token: string | null,
  itemId: string,
): Promise<ClashDetail | null> {
  const res = await apiFetch(`/api/projects/${projectUuid}/clash-workflow/clashes/${itemId}`, { token })
  if (!res.ok) return null
  return (await res.json()) as ClashDetail
}

export async function updateClashWorkflowStatus(
  projectUuid: string,
  token: string | null,
  itemId: string,
  status: ClashStatus,
  comment?: string,
): Promise<boolean> {
  const res = await apiFetch(`/api/projects/${projectUuid}/clash-workflow/clashes/${itemId}/status`, {
    method: 'POST',
    token,
    body: JSON.stringify({ status, comment: comment ?? null }),
  })
  return res.ok
}

export async function recordClashWorkflowDecision(
  projectUuid: string,
  token: string | null,
  itemId: string,
  decision: ReviewerDecision,
  comment?: string,
): Promise<boolean> {
  const res = await apiFetch(`/api/projects/${projectUuid}/clash-workflow/clashes/${itemId}/decision`, {
    method: 'POST',
    token,
    body: JSON.stringify({ decision, comment: comment ?? null }),
  })
  return res.ok
}

export async function addClashWorkflowComment(
  projectUuid: string,
  token: string | null,
  itemId: string,
  comment: string,
): Promise<boolean> {
  const res = await apiFetch(`/api/projects/${projectUuid}/clash-workflow/clashes/${itemId}/comment`, {
    method: 'POST',
    token,
    body: JSON.stringify({ comment }),
  })
  return res.ok
}

export async function uploadClashCorrection(
  projectUuid: string,
  token: string | null,
  itemId: string,
  params: { target: CorrectionTarget; revisionName: string; file: File },
): Promise<ClashDetail | null> {
  const form = new FormData()
  form.set('target', params.target)
  form.set('revision_name', params.revisionName)
  form.set('file', params.file)
  const res = await apiFetch(
    `/api/projects/${projectUuid}/clash-workflow/clashes/${itemId}/corrections`,
    { method: 'POST', token, body: form },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'No se pudo subir la corrección')
  }
  return (await res.json()) as ClashDetail
}

export async function requestClashReanalysis(
  projectUuid: string,
  token: string | null,
  itemId: string,
  outcome?: CorrectionResult,
): Promise<ClashDetail | null> {
  const res = await apiFetch(
    `/api/projects/${projectUuid}/clash-workflow/clashes/${itemId}/reanalysis`,
    { method: 'POST', token, body: JSON.stringify({ outcome: outcome ?? null }) },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'No se pudo reanalizar')
  }
  return (await res.json()) as ClashDetail
}

async function downloadExport(
  token: string | null,
  path: string,
  fallbackFilename: string,
  mime: string,
): Promise<void> {
  const res = await apiFetch(path, { token })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'Error al descargar')
  }
  const blob = await res.blob()
  if (blob.type === 'application/json') {
    const err = await blob.text()
    throw new Error(err)
  }
  downloadBlob(new Blob([blob], { type: mime }), filenameFromContentDisposition(res, fallbackFilename))
}

export async function downloadClashTechnicalExcel(
  projectUuid: string,
  token: string | null,
  jobId?: string,
): Promise<void> {
  const path = jobId
    ? `/api/projects/${projectUuid}/clash/jobs/${jobId}/exports/technical.xlsx`
    : `/api/projects/${projectUuid}/clash/jobs/latest/exports/technical.xlsx`
  await downloadExport(
    token,
    path,
    `reporte-tecnico-corrida-${projectUuid}.xlsx`,
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  )
}

export async function downloadFinalTechnicalPdf(
  projectUuid: string,
  token: string | null,
): Promise<void> {
  await downloadExport(
    token,
    `/api/projects/${projectUuid}/clash/jobs/latest/exports/final-technical.pdf`,
    `informe-tecnico-final-${projectUuid}.pdf`,
    'application/pdf',
  )
}

export async function downloadFinalTechnicalExcel(
  projectUuid: string,
  token: string | null,
): Promise<void> {
  await downloadExport(
    token,
    `/api/projects/${projectUuid}/clash/jobs/latest/exports/final-technical.xlsx`,
    `informe-tecnico-final-${projectUuid}.xlsx`,
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  )
}

export async function downloadFinalHumanPdf(
  projectUuid: string,
  token: string | null,
): Promise<void> {
  await downloadExport(
    token,
    `/api/projects/${projectUuid}/clash/jobs/latest/exports/final-human.pdf`,
    `informe-final-${projectUuid}.pdf`,
    'application/pdf',
  )
}

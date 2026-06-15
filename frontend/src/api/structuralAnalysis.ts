import { apiFetch } from './client'
import { downloadBlob, filenameFromContentDisposition } from '../lib/download'
import type { ClashJob } from '../types/clashJob'
import type { StructuralAnalysisReport } from '../types/structuralAnalysisReport'

export type CoordinationFolderOption = {
  uuid: string
  name: string
  path: string
  parent_uuid: string | null
}

export type CoordinationInventory = {
  project_name: string
  folder: { uuid: string; name: string; path: string } | null
  files_by_discipline: Record<
    string,
    Array<{
      uuid: string
      file_name: string
      discipline: string | null
      discipline_bucket: string
      folder_path: string
      status: string
    }>
  >
  discipline_lines: Array<{ bucket: string; label: string; short: string; count: number }>
  summary: {
    total_cad: number
    sin_clasificar: number
    discipline_count: number
    by_bucket: Record<string, number>
  }
  ready: boolean
  blockers: string[]
}

export async function getCoordinationFolders(
  projectUuid: string,
  token: string | null,
): Promise<CoordinationFolderOption[]> {
  const res = await apiFetch(`/api/projects/${projectUuid}/coordination/folders`, { token })
  if (!res.ok) return []
  return (await res.json()) as CoordinationFolderOption[]
}

export async function getCoordinationInventory(
  projectUuid: string,
  token: string | null,
  folderUuid: string | null,
): Promise<CoordinationInventory | null> {
  const q = folderUuid ? `?folder_uuid=${encodeURIComponent(folderUuid)}` : ''
  const res = await apiFetch(`/api/projects/${projectUuid}/coordination/inventory${q}`, { token })
  if (!res.ok) return null
  return (await res.json()) as CoordinationInventory
}

export async function getProjectFilesCount(projectUuid: string, token: string | null): Promise<number | null> {
  const res = await apiFetch(`/api/projects/${projectUuid}/files/count`, { token })
  if (!res.ok) return null
  const j = (await res.json()) as { total?: number }
  return typeof j.total === 'number' ? j.total : null
}

export async function enqueueClashJob(
  projectUuid: string,
  token: string | null,
  opts?: { folder_uuid?: string },
): Promise<ClashJob> {
  const res = await apiFetch(`/api/projects/${projectUuid}/clash/jobs`, {
    method: 'POST',
    token,
    body: JSON.stringify({
      folder_uuid: opts?.folder_uuid ?? null,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'Error al encolar el análisis de clashes')
  }
  return (await res.json()) as ClashJob
}

export async function getLatestClashJob(
  projectUuid: string,
  token: string | null,
): Promise<ClashJob | null> {
  const res = await apiFetch(`/api/projects/${projectUuid}/clash/jobs/latest`, { token })
  if (res.status === 404) return null
  if (!res.ok) return null
  return (await res.json()) as ClashJob
}

export async function getStructuralAnalysisReport(
  projectUuid: string,
  token: string | null,
): Promise<StructuralAnalysisReport | null> {
  const res = await apiFetch(`/api/projects/${projectUuid}/structural-analysis-report`, { token })
  if (res.status === 404) return null
  if (!res.ok) return null
  return (await res.json()) as StructuralAnalysisReport
}

async function downloadClashPdf(
  token: string | null,
  path: string,
  fallbackFilename: string,
): Promise<void> {
  const res = await apiFetch(path, { token })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'Error al descargar el PDF')
  }
  const blob = await res.blob()
  downloadBlob(blob, filenameFromContentDisposition(res, fallbackFilename))
}

export async function downloadClashTechnicalPdf(
  projectUuid: string,
  token: string | null,
  jobId?: string,
): Promise<void> {
  const path = jobId
    ? `/api/projects/${projectUuid}/clash/jobs/${jobId}/exports/technical.pdf`
    : `/api/projects/${projectUuid}/clash/jobs/latest/exports/technical.pdf`
  await downloadClashPdf(token, path, `reporte-tecnico-clashes-${projectUuid}.pdf`)
}

export async function downloadClashHumanPdf(
  projectUuid: string,
  token: string | null,
  jobId?: string,
): Promise<void> {
  const path = jobId
    ? `/api/projects/${projectUuid}/clash/jobs/${jobId}/exports/human.pdf`
    : `/api/projects/${projectUuid}/clash/jobs/latest/exports/human.pdf`
  await downloadClashPdf(token, path, `reporte-humano-clashes-${projectUuid}.pdf`)
}

import { useCallback, useEffect, useState } from 'react'
import { FilePlus, Filter, FolderPlus, LayoutGrid, List, Pencil, Trash2 } from 'lucide-react'

import { apiFetch } from '../../../api/client'
import {
  filterAllowedProjectFiles,
  formatAllowedProjectExtensionsHint,
  isAllowedProjectFileName,
} from '../../../constants/projectAllowedFiles'
import {
  PROJECT_FILE_DISCIPLINE_LABELS,
  PROJECT_FILE_DISCIPLINE_VALUES,
  type ProjectFileDisciplineValue,
} from '../../../constants/projectFileDisciplines'
import { downloadBlob } from '../../../lib/download'
import { confirmDestructive } from '../../../lib/duplaAlert'
import {
  BUDGET_EXCLUDED_FILE_BADGE,
  BUDGET_EXCLUDED_UPLOAD_NOTICE,
  uploadsExcludedFromBudget,
} from '../../../lib/projectFileBudget'
import type { ProjectFileFolderRow, ProjectFileRow, ProjectFileSearchRow } from '../../../types/projectWorkspace'
import { Card } from '../../Card'
import { WorkspaceActionButton } from '../WorkspaceActionButton'
import { ProjectFilesUploadWizard } from '../ProjectFilesUploadWizard'
import { ProjectWorkspaceFileIcon } from '../ProjectWorkspaceFileIcon'

type TrailSeg = { uuid: string | null; name: string }

const FILES_PAGE_SIZE = 50

type FilesListPayload = {
  items: ProjectFileRow[]
  total: number
  limit: number
  offset: number
}

type WorkspaceArchivosTabProps = {
  projectUuid: string
  token: string | null
  workflowPhase: string
  flowMsg: string | null
}

const PROJECT_FILE_CATEGORY_LABELS: Record<string, string> = {
  PDF_DOCUMENT: 'PDF',
  CAD_DRAWING: 'CAD',
  BIM_MODEL: 'BIM',
  LEGAL_TECHNICAL: 'Téc.-legal',
}

function disciplineLabel(raw: string | null | undefined): string | null {
  if (!raw) return null
  const v = raw as ProjectFileDisciplineValue
  return PROJECT_FILE_DISCIPLINE_LABELS[v] ?? raw
}

function isFileClassifying(f: { ingest_status: string; discipline?: string | null; discipline_classifying?: boolean }): boolean {
  if (typeof f.discipline_classifying === 'boolean') return f.discipline_classifying
  return f.ingest_status === 'PUBLISHED' && !f.discipline?.trim()
}

function disciplineBadgeText(f: { ingest_status: string; discipline?: string | null }): string {
  if (isFileClassifying(f)) return 'Clasificando…'
  return disciplineLabel(f.discipline) ?? 'Sin clasificar'
}

function fileCategoryLabel(raw: string | null | undefined): string | null {
  if (!raw?.trim()) return null
  return PROJECT_FILE_CATEGORY_LABELS[raw] ?? raw
}

function formatUploadedAt(iso: string) {
  try {
    return new Date(iso).toLocaleString('es-ES', {
      dateStyle: 'short',
      timeStyle: 'short',
    })
  } catch {
    return iso
  }
}

export function WorkspaceArchivosTab({ projectUuid, token, workflowPhase, flowMsg }: WorkspaceArchivosTabProps) {
  const [folderUuid, setFolderUuid] = useState<string | null>(null)
  const [trail, setTrail] = useState<TrailSeg[]>([{ uuid: null, name: 'Raíz' }])
  const [folders, setFolders] = useState<ProjectFileFolderRow[]>([])
  const [files, setFiles] = useState<ProjectFileRow[]>([])
  const [filesTotal, setFilesTotal] = useState(0)
  const [filePageOffset, setFilePageOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  const [wizardOpen, setWizardOpen] = useState(false)
  const [dropHighlight, setDropHighlight] = useState(false)
  const [pendingDropFiles, setPendingDropFiles] = useState<File[] | undefined>(undefined)
  const [folderModalOpen, setFolderModalOpen] = useState(false)
  const [folderModalName, setFolderModalName] = useState('')
  const [filterOpen, setFilterOpen] = useState(false)
  const [filterDiscipline, setFilterDiscipline] = useState<string>('')
  const [filterSearch, setFilterSearch] = useState('')
  const [searchHits, setSearchHits] = useState<ProjectFileSearchRow[] | null>(null)
  const [searchBusy, setSearchBusy] = useState(false)
  const [dragFileId, setDragFileId] = useState<string | null>(null)
  const [fileView, setFileView] = useState<'grid' | 'list'>('grid')
  const [fileNotice, setFileNotice] = useState<string | null>(null)
  const [editingFile, setEditingFile] = useState<ProjectFileRow | ProjectFileSearchRow | null>(null)
  const [editFileName, setEditFileName] = useState('')
  const [editFileDescription, setEditFileDescription] = useState('')
  const [editSaving, setEditSaving] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!token || !projectUuid) return
    setBusy(true)
    try {
      const fq =
        folderUuid === null
          ? ''
          : `?parent_uuid=${encodeURIComponent(folderUuid)}`
      const fileParams = new URLSearchParams()
      if (folderUuid !== null) fileParams.set('folder_uuid', folderUuid)
      fileParams.set('limit', String(FILES_PAGE_SIZE))
      fileParams.set('offset', String(filePageOffset))
      const filesUrl = `/api/projects/${projectUuid}/files?${fileParams.toString()}`
      const [fr, fe] = await Promise.all([
        apiFetch(`/api/projects/${projectUuid}/file-folders${fq}`, { token }),
        apiFetch(filesUrl, { token }),
      ])
      if (fr.ok) setFolders((await fr.json()) as ProjectFileFolderRow[])
      if (fe.ok) {
        const data = (await fe.json()) as FilesListPayload
        setFiles(data.items)
        setFilesTotal(data.total)
        if (data.items.length === 0 && data.total > 0 && data.offset >= data.total) {
          setFilePageOffset(0)
        }
      }
    } finally {
      setBusy(false)
    }
  }, [token, projectUuid, folderUuid, filePageOffset])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!token || !projectUuid) return
    void apiFetch(`/api/projects/${projectUuid}/files/reconcile-ingest`, { method: 'POST', token })
  }, [projectUuid, token])

  function enterFolder(f: ProjectFileFolderRow) {
    setFilePageOffset(0)
    setFolderUuid(f.uuid)
    setTrail((t) => [...t, { uuid: f.uuid, name: f.name }])
  }

  function goTrail(i: number) {
    setFilePageOffset(0)
    const next = trail.slice(0, i + 1)
    setTrail(next)
    const last = next[next.length - 1]
    setFolderUuid(last?.uuid ?? null)
  }

  const loadSearchResults = useCallback(async () => {
    if (!token || !projectUuid) return
    const params = new URLSearchParams()
    if (filterSearch.trim()) params.set('q', filterSearch.trim())
    if (filterDiscipline) params.set('discipline', filterDiscipline)
    const res = await apiFetch(`/api/projects/${projectUuid}/files/search?${params.toString()}`, { token })
    if (res.ok) setSearchHits((await res.json()) as ProjectFileSearchRow[])
    else setSearchHits([])
  }, [token, projectUuid, filterSearch, filterDiscipline])

  const hasActiveFilters = Boolean(filterDiscipline || filterSearch.trim())

  useEffect(() => {
    if (hasActiveFilters) setFilePageOffset(0)
  }, [hasActiveFilters])

  useEffect(() => {
    if (!hasActiveFilters) {
      setSearchHits(null)
      setSearchBusy(false)
      return
    }
    let cancelled = false
    setSearchBusy(true)
    const t = window.setTimeout(() => {
      void (async () => {
        try {
          await loadSearchResults()
        } finally {
          if (!cancelled) setSearchBusy(false)
        }
      })()
    }, 300)
    return () => {
      cancelled = true
      window.clearTimeout(t)
    }
  }, [hasActiveFilters, loadSearchResults])

  useEffect(() => {
    const pending =
      files.some(isFileClassifying) || (searchHits?.some(isFileClassifying) ?? false)
    if (!pending || !token) return
    const timer = window.setInterval(() => {
      void load()
      if (hasActiveFilters) void loadSearchResults()
    }, 5000)
    return () => window.clearInterval(timer)
  }, [files, searchHits, token, load, hasActiveFilters, loadSearchResults])

  async function createFolderFromModal(): Promise<boolean> {
    if (!token || !folderModalName.trim()) return false
    const res = await apiFetch(`/api/projects/${projectUuid}/file-folders`, {
      method: 'POST',
      token,
      body: JSON.stringify({ name: folderModalName.trim(), parent_uuid: folderUuid }),
    })
    if (!res.ok) return false
    setFolderModalName('')
    setFolderModalOpen(false)
    await load()
    return true
  }

  async function deleteFolder(f: ProjectFileFolderRow) {
    if (!token) return
    if (
      !(await confirmDestructive({
        title: `¿Eliminar carpeta "${f.name}"?`,
        text: 'La carpeta debe estar vacía.',
      }))
    ) {
      return
    }
    const res = await apiFetch(`/api/projects/${projectUuid}/file-folders/${f.uuid}`, {
      method: 'DELETE',
      token,
    })
    if (!res.ok) return
    await load()
  }

  async function deleteFile(f: ProjectFileRow) {
    if (!token) return
    if (
      !(await confirmDestructive({
        title: `¿Eliminar "${f.original_name}"?`,
      }))
    ) {
      return
    }
    const res = await apiFetch(`/api/projects/${projectUuid}/files/${f.uuid}`, {
      method: 'DELETE',
      token,
    })
    if (!res.ok) return
    if (hasActiveFilters) await loadSearchResults()
    await load()
  }

  async function downloadFile(f: ProjectFileRow) {
    if (!token) return
    const res = await apiFetch(`/api/projects/${projectUuid}/files/${f.uuid}/download`, { token })
    if (!res.ok) return
    const blob = await res.blob()
    downloadBlob(blob, f.original_name)
  }

  async function moveFileToFolder(fileUuid: string, targetFolderUuid: string | null) {
    if (!token) return
    const res = await apiFetch(`/api/projects/${projectUuid}/files/${fileUuid}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify({ folder_uuid: targetFolderUuid }),
    })
    if (!res.ok) return
    setDragFileId(null)
    await load()
  }

  function openEditFile(f: ProjectFileRow | ProjectFileSearchRow) {
    setEditingFile(f)
    setEditFileName(f.original_name)
    setEditFileDescription(f.description ?? '')
    setEditError(null)
  }

  async function saveFileEdit(): Promise<boolean> {
    if (!token || !editingFile) return false
    const name = editFileName.trim()
    if (!name) {
      setEditError('El nombre es obligatorio')
      return false
    }
    if (!isAllowedProjectFileName(name)) {
      setEditError(`La extensión debe ser una de: ${formatAllowedProjectExtensionsHint()}`)
      return false
    }
    setEditSaving(true)
    setEditError(null)
    try {
      const res = await apiFetch(`/api/projects/${projectUuid}/files/${editingFile.uuid}`, {
        method: 'PATCH',
        token,
        body: JSON.stringify({
          original_name: name,
          description: editFileDescription.trim() || null,
        }),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setEditError((j as { detail?: string }).detail ?? 'No se pudo guardar')
        return false
      }
      setEditingFile(null)
      if (hasActiveFilters) await loadSearchResults()
      await load()
      return true
    } finally {
      setEditSaving(false)
    }
  }

  const showBudgetExcludedNotice = uploadsExcludedFromBudget(workflowPhase)

  const budgetExcludedBadge = (countsForBudget: boolean | undefined) =>
    countsForBudget === false ? (
      <span
        className="rounded bg-amber-100 px-1 py-0.5 text-[9px] font-semibold uppercase text-amber-900"
        title={BUDGET_EXCLUDED_UPLOAD_NOTICE}
      >
        {BUDGET_EXCLUDED_FILE_BADGE}
      </span>
    ) : null

  const currentFolderLabel = trail[trail.length - 1]?.name ?? 'Raíz'

  const fileHasPrevPage = filePageOffset > 0
  const fileHasNextPage = filePageOffset + files.length < filesTotal
  const showFilePagination =
    !hasActiveFilters && filesTotal > 20 && (fileHasPrevPage || fileHasNextPage)

  return (
    <Card data-tour="workspace-archivos-root" className="flex min-h-0 w-full flex-1 flex-col gap-4 p-6">
      <div className="shrink-0">
        <h2 className="text-lg font-semibold text-ink">Archivos del proyecto</h2>
        <p className="text-sm text-muted">
          Formatos de subida: {formatAllowedProjectExtensionsHint()}. Explorador por carpetas; puedes editar nombre y
          descripción tras subir. Los cambios quedan en el historial del proyecto.
        </p>
        {showBudgetExcludedNotice ? (
          <p className="mt-2 rounded-md border border-amber-200/80 bg-amber-50 px-3 py-2 text-sm text-amber-950">
            {BUDGET_EXCLUDED_UPLOAD_NOTICE}
          </p>
        ) : null}
        {fileNotice ? (
          <p className="mt-2 text-sm font-medium text-primary" role="status">
            {fileNotice}{' '}
            <button type="button" className="du-link text-sm font-normal" onClick={() => setFileNotice(null)}>
              Cerrar
            </button>
          </p>
        ) : null}
      </div>

      <div
        data-tour="workspace-archivos-toolbar"
        className="flex shrink-0 flex-wrap items-center justify-between gap-3"
      >
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className={`inline-flex shrink-0 items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium shadow-sm ${
              hasActiveFilters
                ? 'border-primary/40 bg-primary/[0.06] text-primary'
                : 'border-black/15 bg-white text-ink hover:bg-black/[0.03]'
            }`}
            aria-expanded={filterOpen}
            onClick={() => setFilterOpen((o) => !o)}
          >
            <Filter className="h-4 w-4" aria-hidden />
            Filtrar
          </button>
          {showFilePagination ? (
            <>
              {fileHasPrevPage ? (
                <button
                  type="button"
                  className="rounded-lg border border-black/15 bg-white px-3 py-2 text-sm font-medium text-ink shadow-sm hover:bg-black/[0.03]"
                  onClick={() => setFilePageOffset((o) => Math.max(0, o - FILES_PAGE_SIZE))}
                >
                  Ver archivos anteriores
                </button>
              ) : null}
              {fileHasNextPage ? (
                <button
                  type="button"
                  className="rounded-lg border border-black/15 bg-white px-3 py-2 text-sm font-medium text-ink shadow-sm hover:bg-black/[0.03]"
                  onClick={() => setFilePageOffset((o) => o + FILES_PAGE_SIZE)}
                >
                  Ver próximos archivos
                </button>
              ) : null}
            </>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-white shadow-sm outline-none transition hover:opacity-90 focus-visible:ring-2 focus-visible:ring-primary/45 focus-visible:ring-offset-2"
            onClick={() => setWizardOpen(true)}
          >
            <FilePlus className="h-4 w-4 shrink-0" aria-hidden />
            Crear archivo
          </button>
          <button
            type="button"
            className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-black/15 bg-white px-3 py-2 text-sm font-medium text-ink shadow-sm hover:bg-black/[0.03]"
            onClick={() => {
              setFolderModalName('')
              setFolderModalOpen(true)
            }}
          >
            <FolderPlus className="h-4 w-4 text-muted" aria-hidden />
            Crear carpeta
          </button>
          <div
            className="inline-flex shrink-0 rounded-lg border border-black/15 bg-white p-0.5 shadow-sm"
            role="group"
            aria-label="Vista de archivos"
          >
            <button
              type="button"
              aria-pressed={fileView === 'grid'}
              title="Vista de cuadrícula"
              className={`rounded-md p-2 outline-none transition ${
                fileView === 'grid'
                  ? 'bg-primary/10 text-primary shadow-sm'
                  : 'text-muted hover:bg-black/[0.04] hover:text-ink'
              } focus-visible:ring-2 focus-visible:ring-primary/35`}
              onClick={() => setFileView('grid')}
            >
              <LayoutGrid className="h-4 w-4" aria-hidden />
            </button>
            <button
              type="button"
              aria-pressed={fileView === 'list'}
              title="Vista de lista"
              className={`rounded-md p-2 outline-none transition ${
                fileView === 'list'
                  ? 'bg-primary/10 text-primary shadow-sm'
                  : 'text-muted hover:bg-black/[0.04] hover:text-ink'
              } focus-visible:ring-2 focus-visible:ring-primary/35`}
              onClick={() => setFileView('list')}
            >
              <List className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </div>
      </div>

      {filterOpen ? (
        <div className="flex shrink-0 flex-wrap items-end gap-3 rounded-lg border border-black/10 bg-black/[0.02] p-3">
          <div className="min-w-[10rem] flex-1">
            <label htmlFor="archivos-filter-discipline" className="du-label text-xs">
              Disciplina
            </label>
            <select
              id="archivos-filter-discipline"
              className="du-input mt-1 w-full text-sm"
              value={filterDiscipline}
              onChange={(e) => setFilterDiscipline(e.target.value)}
            >
              <option value="">Todas</option>
              {PROJECT_FILE_DISCIPLINE_VALUES.map((v) => (
                <option key={v} value={v}>
                  {PROJECT_FILE_DISCIPLINE_LABELS[v]}
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-[12rem] flex-[2]">
            <label htmlFor="archivos-filter-search" className="du-label text-xs">
              Nombre o descripción
            </label>
            <input
              id="archivos-filter-search"
              className="du-input mt-1 w-full text-sm"
              value={filterSearch}
              onChange={(e) => setFilterSearch(e.target.value)}
              placeholder="Buscar…"
              autoComplete="off"
            />
          </div>
          {hasActiveFilters ? (
            <button
              type="button"
              className="rounded-lg border border-black/15 px-3 py-2 text-sm text-muted hover:bg-white"
              onClick={() => {
                setFilterDiscipline('')
                setFilterSearch('')
              }}
            >
              Limpiar
            </button>
          ) : null}
        </div>
      ) : null}

      {flowMsg ? <p className="shrink-0 text-sm text-primary">{flowMsg}</p> : null}

      {hasActiveFilters ? (
        <p className="shrink-0 text-sm text-muted">
          Búsqueda en todo el proyecto: solo archivos. La ruta muestra la carpeta donde está cada uno.
        </p>
      ) : (
        <nav className="flex shrink-0 flex-wrap items-center gap-1 text-sm" aria-label="Ruta">
          {trail.map((seg, i) => (
            <span key={`${seg.uuid ?? 'root'}-${i}`} className="flex items-center gap-1">
              {i > 0 ? <span className="text-black/25">/</span> : null}
              <button
                type="button"
                className={`rounded px-1 py-0.5 hover:bg-black/5 ${
                  i === trail.length - 1 ? 'font-semibold text-ink' : 'text-primary'
                }`}
                onClick={() => goTrail(i)}
              >
                {seg.name}
              </button>
            </span>
          ))}
        </nav>
      )}

      <div
        data-tour="workspace-archivos-dropzone"
        className={`flex min-h-0 flex-1 flex-col rounded-xl border-2 border-dashed p-4 transition-colors ${
          dropHighlight ? 'border-primary/50 bg-primary/[0.04]' : 'border-black/10 bg-white'
        }`}
        onDragEnter={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setDropHighlight(true)
        }}
        onDragLeave={(e) => {
          e.preventDefault()
          if (e.currentTarget === e.target) setDropHighlight(false)
        }}
        onDragOver={(e) => {
          e.preventDefault()
          e.stopPropagation()
        }}
        onDrop={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setDropHighlight(false)
          if (e.dataTransfer.files?.length) {
            const { allowed, rejected } = filterAllowedProjectFiles(Array.from(e.dataTransfer.files))
            if (rejected.length) {
              setFileNotice(
                `Solo ${formatAllowedProjectExtensionsHint()}. Se ignoraron ${rejected.length} archivo(s).`,
              )
            } else {
              setFileNotice(null)
            }
            if (allowed.length) {
              setPendingDropFiles(allowed)
              setWizardOpen(true)
            }
            return
          }
          if (hasActiveFilters) return
          const id = e.dataTransfer.getData('text/plain')
          if (id && dragFileId) void moveFileToFolder(id, folderUuid)
        }}
      >
        <div className="min-h-0 flex-1 overflow-y-auto">
        {hasActiveFilters ? (
          searchBusy ? (
            <p className="py-8 text-center text-sm text-muted">Buscando…</p>
          ) : searchHits && searchHits.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted">
              Ningún archivo coincide con los filtros. Prueba otro texto o disciplina.
            </p>
          ) : fileView === 'grid' ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-[repeat(auto-fill,minmax(15rem,1fr))]">
              {(searchHits ?? []).map((f) => (
                <div
                  key={f.uuid}
                  className="group relative flex min-w-0 flex-col gap-2 rounded-lg border border-black/10 bg-white p-3.5 shadow-[var(--shadow-card)] transition hover:border-primary/25"
                >
                  <div className="flex items-start gap-3">
                    <ProjectWorkspaceFileIcon name={f.original_name} className="h-8 w-8 shrink-0 text-primary" />
                    <div className="min-w-0 flex-1">
                      <p className="line-clamp-2 text-sm font-medium leading-snug text-ink">{f.original_name}</p>
                      <p className="mt-1 text-xs leading-snug text-primary" title={f.path}>
                        {f.path}
                      </p>
                      <p className="mt-1 text-xs text-muted">Subido: {formatUploadedAt(f.created_at)}</p>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {f.ingest_status === 'DRAFT' ? (
                          <span className="rounded bg-amber-100 px-1 py-0.5 text-[9px] font-semibold uppercase text-amber-900">
                            Borrador
                          </span>
                        ) : null}
                        {budgetExcludedBadge(f.counts_for_budget)}
                        {isFileClassifying(f) ? (
                          <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
                            {disciplineBadgeText(f)}
                          </span>
                        ) : disciplineLabel(f.discipline) ? (
                          <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                            {disciplineBadgeText(f)}
                          </span>
                        ) : (
                          <span className="text-[10px] text-muted">{disciplineBadgeText(f)}</span>
                        )}
                        {fileCategoryLabel(f.category) ? (
                          <span className="rounded-full bg-black/[0.06] px-1.5 py-0.5 text-[10px] font-medium text-ink">
                            {fileCategoryLabel(f.category)}
                          </span>
                        ) : null}
                      </div>
                      {f.description ? (
                        <p className="mt-1 line-clamp-2 text-xs leading-snug text-muted">{f.description}</p>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 border-t border-black/5 pt-2">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-ink hover:underline"
                      onClick={() => openEditFile(f)}
                    >
                      <Pencil className="h-3 w-3" aria-hidden />
                      Editar
                    </button>
                    <button
                      type="button"
                      className="text-xs font-semibold text-primary hover:underline"
                      onClick={() => void downloadFile(f)}
                    >
                      Descargar
                    </button>
                    <button
                      type="button"
                      className="text-xs font-semibold text-red-700 hover:underline"
                      onClick={() => void deleteFile(f)}
                    >
                      Eliminar
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[min(100%,28rem)] border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-black/10 text-[11px] font-semibold uppercase tracking-wide text-muted">
                    <th className="py-2 pr-2">Nombre</th>
                    <th className="py-2 pr-2">Ubicación / datos</th>
                    <th className="w-40 py-2 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {(searchHits ?? []).map((f) => (
                    <tr key={f.uuid} className="border-b border-black/5 hover:bg-black/[0.02]">
                      <td className="max-w-[12rem] py-2 pr-2 align-top">
                        <div className="flex items-start gap-2">
                          <ProjectWorkspaceFileIcon name={f.original_name} className="h-7 w-7 shrink-0 text-primary" />
                          <span className="min-w-0 font-medium leading-snug text-ink">{f.original_name}</span>
                        </div>
                      </td>
                      <td className="py-2 pr-2 align-top text-[11px] text-muted">
                        <p className="text-primary" title={f.path}>
                          {f.path}
                        </p>
                        <p>Subido: {formatUploadedAt(f.created_at)}</p>
                        {f.ingest_status === 'DRAFT' ? (
                          <span className="mt-1 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-900">
                            Borrador
                          </span>
                        ) : null}
                        <span className="mt-1 inline-block">{budgetExcludedBadge(f.counts_for_budget)}</span>
                        {isFileClassifying(f) ? (
                          <span className="mt-1 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-900">
                            {disciplineBadgeText(f)}
                          </span>
                        ) : disciplineLabel(f.discipline) ? (
                          <span className="mt-1 inline-block rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                            {disciplineBadgeText(f)}
                          </span>
                        ) : (
                          <span className="mt-1 block text-[11px]">{disciplineBadgeText(f)}</span>
                        )}
                        {fileCategoryLabel(f.category) ? (
                          <span className="mt-1 inline-block rounded-full bg-black/[0.06] px-2 py-0.5 text-[11px] font-medium text-ink">
                            {fileCategoryLabel(f.category)}
                          </span>
                        ) : null}
                        {f.description ? <p className="mt-1 line-clamp-2 text-muted">{f.description}</p> : null}
                      </td>
                      <td className="whitespace-nowrap py-2 text-right align-top">
                        <button
                          type="button"
                          className="mr-2 inline-flex items-center gap-1 font-semibold text-ink hover:underline"
                          onClick={() => openEditFile(f)}
                        >
                          <Pencil className="h-3 w-3" aria-hidden />
                          Editar
                        </button>
                        <button
                          type="button"
                          className="font-semibold text-primary hover:underline"
                          onClick={() => void downloadFile(f)}
                        >
                          Descargar
                        </button>
                        <span className="mx-1 text-black/15">·</span>
                        <button
                          type="button"
                          className="font-semibold text-red-700 hover:underline"
                          onClick={() => void deleteFile(f)}
                        >
                          Eliminar
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : busy ? (
          <p className="text-sm text-muted">Cargando…</p>
        ) : folders.length === 0 && files.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted">
            Carpeta vacía. Crea una carpeta, un archivo o arrastra aquí.
          </p>
        ) : fileView === 'grid' ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[repeat(auto-fill,minmax(15rem,1fr))]">
            {folders.map((fo) => (
              <div
                key={fo.uuid}
                role="button"
                tabIndex={0}
                className="group relative flex min-w-0 flex-col gap-2 rounded-lg border border-black/10 bg-white p-3.5 text-left shadow-[var(--shadow-card)] transition hover:border-primary/25"
                onDoubleClick={() => enterFolder(fo)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') enterFolder(fo)
                }}
                onDragOver={(e) => {
                  e.preventDefault()
                  if (dragFileId) e.dataTransfer.dropEffect = 'move'
                }}
                onDrop={(e) => {
                  e.preventDefault()
                  const id = e.dataTransfer.getData('text/plain')
                  if (id && dragFileId) void moveFileToFolder(id, fo.uuid)
                }}
              >
                <div className="flex items-start gap-3">
                  <ProjectWorkspaceFileIcon isFolder name={fo.name} className="h-8 w-8 shrink-0 text-amber-600/90" />
                  <div className="min-w-0 flex-1">
                    <p className="break-words text-sm font-medium leading-snug text-ink line-clamp-2">{fo.name}</p>
                    <p className="mt-1 text-xs text-muted">Carpeta · doble clic</p>
                  </div>
                  <button
                    type="button"
                    className="shrink-0 rounded p-1 text-muted opacity-0 hover:bg-red-50 hover:text-red-700 group-hover:opacity-100"
                    title="Eliminar carpeta"
                    onClick={(e) => {
                      e.stopPropagation()
                      void deleteFolder(fo)
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  </button>
                </div>
              </div>
            ))}

            {files.map((f) => (
              <div
                key={f.uuid}
                draggable
                className="group relative flex min-w-0 flex-col gap-2 rounded-lg border border-black/10 bg-white p-3.5 shadow-[var(--shadow-card)] transition hover:border-primary/25"
                onDragStart={(e) => {
                  setDragFileId(f.uuid)
                  e.dataTransfer.setData('text/plain', f.uuid)
                  e.dataTransfer.effectAllowed = 'move'
                }}
                onDragEnd={() => setDragFileId(null)}
              >
                <div className="flex items-start gap-3">
                  <ProjectWorkspaceFileIcon name={f.original_name} className="h-8 w-8 shrink-0 text-primary" />
                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-2 text-sm font-medium leading-snug text-ink">{f.original_name}</p>
                    <p className="mt-1 text-xs text-muted">Subido: {formatUploadedAt(f.created_at)}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {f.ingest_status === 'DRAFT' ? (
                        <span className="rounded bg-amber-100 px-1 py-0.5 text-[9px] font-semibold uppercase text-amber-900">
                          Borrador
                        </span>
                      ) : null}
                      {budgetExcludedBadge(f.counts_for_budget)}
                      {isFileClassifying(f) ? (
                        <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
                          {disciplineBadgeText(f)}
                        </span>
                      ) : disciplineLabel(f.discipline) ? (
                        <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                          {disciplineBadgeText(f)}
                        </span>
                      ) : (
                        <span className="text-[10px] text-muted">{disciplineBadgeText(f)}</span>
                      )}
                      {fileCategoryLabel(f.category) ? (
                        <span className="rounded-full bg-black/[0.06] px-1.5 py-0.5 text-[10px] font-medium text-ink">
                          {fileCategoryLabel(f.category)}
                        </span>
                      ) : null}
                    </div>
                    {f.description ? (
                      <p className="mt-1 line-clamp-2 text-xs leading-snug text-muted">{f.description}</p>
                    ) : (
                      <p className="mt-1 text-xs italic text-muted">Sin descripción</p>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 border-t border-black/5 pt-2">
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 text-xs font-semibold text-ink hover:underline"
                    onClick={() => openEditFile(f)}
                  >
                    <Pencil className="h-3 w-3" aria-hidden />
                    Editar
                  </button>
                  <button
                    type="button"
                    className="text-xs font-semibold text-primary hover:underline"
                    onClick={() => void downloadFile(f)}
                  >
                    Descargar
                  </button>
                  <button
                    type="button"
                    className="text-xs font-semibold text-red-700 hover:underline"
                    onClick={() => void deleteFile(f)}
                  >
                    Eliminar
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[min(100%,32rem)] border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-black/10 text-[11px] font-semibold uppercase tracking-wide text-muted">
                  <th className="py-2 pr-2">Nombre</th>
                  <th className="py-2 pr-2">Detalles</th>
                  <th className="w-40 py-2 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {folders.map((fo) => (
                  <tr
                    key={fo.uuid}
                    role="button"
                    tabIndex={0}
                    className="cursor-pointer border-b border-black/5 hover:bg-black/[0.02]"
                    onDoubleClick={() => enterFolder(fo)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') enterFolder(fo)
                    }}
                    onDragOver={(e) => {
                      e.preventDefault()
                      if (dragFileId) e.dataTransfer.dropEffect = 'move'
                    }}
                    onDrop={(e) => {
                      e.preventDefault()
                      const id = e.dataTransfer.getData('text/plain')
                      if (id && dragFileId) void moveFileToFolder(id, fo.uuid)
                    }}
                  >
                    <td className="max-w-[14rem] py-2 pr-2 align-middle">
                      <div className="flex items-center gap-2">
                        <ProjectWorkspaceFileIcon isFolder name={fo.name} className="h-7 w-7 shrink-0 text-amber-600/90" />
                        <span className="min-w-0 font-medium text-ink">{fo.name}</span>
                      </div>
                    </td>
                    <td className="py-2 pr-2 align-middle text-[11px] text-muted">
                      Carpeta · doble clic para abrir
                    </td>
                    <td className="py-2 text-right align-middle">
                      <button
                        type="button"
                        className="rounded p-1 text-muted hover:bg-red-50 hover:text-red-700"
                        title="Eliminar carpeta"
                        onClick={(e) => {
                          e.stopPropagation()
                          void deleteFolder(fo)
                        }}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden />
                      </button>
                    </td>
                  </tr>
                ))}
                {files.map((f) => (
                  <tr
                    key={f.uuid}
                    draggable
                    className="border-b border-black/5 hover:bg-black/[0.02]"
                    onDragStart={(e) => {
                      setDragFileId(f.uuid)
                      e.dataTransfer.setData('text/plain', f.uuid)
                      e.dataTransfer.effectAllowed = 'move'
                    }}
                    onDragEnd={() => setDragFileId(null)}
                  >
                    <td className="max-w-[14rem] py-2 pr-2 align-top">
                      <div className="flex items-start gap-2">
                        <ProjectWorkspaceFileIcon name={f.original_name} className="h-7 w-7 shrink-0 text-primary" />
                        <span className="min-w-0 font-medium leading-snug text-ink">{f.original_name}</span>
                      </div>
                    </td>
                    <td className="py-2 pr-2 align-top text-[11px] text-muted">
                      <p>Subido: {formatUploadedAt(f.created_at)}</p>
                      {f.ingest_status === 'DRAFT' ? (
                        <span className="mt-1 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-900">
                          Borrador
                        </span>
                      ) : null}
                      <span className="mt-1 inline-block">{budgetExcludedBadge(f.counts_for_budget)}</span>
                      {isFileClassifying(f) ? (
                        <span className="mt-1 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-900">
                          {disciplineBadgeText(f)}
                        </span>
                      ) : disciplineLabel(f.discipline) ? (
                        <span className="mt-1 inline-block rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                          {disciplineBadgeText(f)}
                        </span>
                      ) : (
                        <span className="mt-1 block">{disciplineBadgeText(f)}</span>
                      )}
                      {fileCategoryLabel(f.category) ? (
                        <span className="mt-1 inline-block rounded-full bg-black/[0.06] px-2 py-0.5 text-[11px] font-medium text-ink">
                          {fileCategoryLabel(f.category)}
                        </span>
                      ) : null}
                      {f.description ? <p className="mt-1 line-clamp-2 text-muted">{f.description}</p> : null}
                    </td>
                    <td className="whitespace-nowrap py-2 text-right align-top">
                      <button
                        type="button"
                        className="mr-2 inline-flex items-center gap-1 font-semibold text-ink hover:underline"
                        onClick={() => openEditFile(f)}
                      >
                        <Pencil className="h-3 w-3" aria-hidden />
                        Editar
                      </button>
                      <button
                        type="button"
                        className="font-semibold text-primary hover:underline"
                        onClick={() => void downloadFile(f)}
                      >
                        Descargar
                      </button>
                      <span className="mx-1 text-black/15">·</span>
                      <button
                        type="button"
                        className="font-semibold text-red-700 hover:underline"
                        onClick={() => void deleteFile(f)}
                      >
                        Eliminar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        </div>
      </div>

      <p className="shrink-0 text-xs text-muted">
        {hasActiveFilters
          ? 'Sal de los filtros (Limpiar) para volver a la vista por carpetas y mover archivos.'
          : 'Arrastra un archivo sobre una carpeta para moverlo. Doble clic en una carpeta para abrirla.'}
      </p>

      <ProjectFilesUploadWizard
        open={wizardOpen}
        onClose={() => {
          setWizardOpen(false)
          setPendingDropFiles(undefined)
        }}
        projectUuid={projectUuid}
        token={token}
        workflowPhase={workflowPhase}
        defaultFolderUuid={folderUuid}
        defaultFolderLabel={currentFolderLabel}
        initialFiles={pendingDropFiles}
        onCompleted={() => void load()}
      />

      {editingFile ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setEditingFile(null)
          }}
        >
          <div
            className="w-full max-w-md rounded-xl border border-black/10 bg-white p-6 shadow-xl"
            role="dialog"
            aria-labelledby="file-edit-title"
            aria-modal="true"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h3 id="file-edit-title" className="text-lg font-semibold text-ink">
              Editar archivo
            </h3>
            <p className="mt-1 text-sm text-muted">
              El nombre debe conservar una extensión permitida ({formatAllowedProjectExtensionsHint()}).
            </p>
            <label htmlFor="file-edit-name" className="du-label mt-4 block text-xs">
              Nombre
            </label>
            <input
              id="file-edit-name"
              className="du-input mt-1 w-full text-sm"
              value={editFileName}
              onChange={(e) => setEditFileName(e.target.value)}
              autoFocus
            />
            <label htmlFor="file-edit-desc" className="du-label mt-4 block text-xs">
              Descripción
            </label>
            <textarea
              id="file-edit-desc"
              className="du-input mt-1 min-h-[100px] w-full resize-y text-sm"
              value={editFileDescription}
              onChange={(e) => setEditFileDescription(e.target.value)}
              maxLength={8000}
              placeholder="Opcional"
            />
            {editError ? (
              <p className="mt-3 text-sm font-medium text-primary" role="alert">
                {editError}
              </p>
            ) : null}
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-black/15 px-4 py-2 text-sm font-medium hover:bg-black/5"
                disabled={editSaving}
                onClick={() => setEditingFile(null)}
              >
                Cancelar
              </button>
              <WorkspaceActionButton
                type="button"
                disabled={editSaving}
                onAction={saveFileEdit}
                successLabel="Archivo guardado"
                runningLabel="Guardando…"
              >
                Guardar
              </WorkspaceActionButton>
            </div>
          </div>
        </div>
      ) : null}

      {folderModalOpen ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setFolderModalOpen(false)
          }}
        >
          <div
            className="w-full max-w-md rounded-xl border border-black/10 bg-white p-6 shadow-xl"
            role="dialog"
            aria-labelledby="folder-modal-title"
            aria-modal="true"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h3 id="folder-modal-title" className="text-lg font-semibold text-ink">
              Nueva carpeta
            </h3>
            <p className="mt-1 text-sm text-muted">
              Se creará dentro de &ldquo;{currentFolderLabel}&rdquo;.
            </p>
            <label htmlFor="folder-modal-name" className="du-label mt-4 block text-xs">
              Nombre
            </label>
            <input
              id="folder-modal-name"
              className="du-input mt-1 w-full text-sm"
              value={folderModalName}
              onChange={(e) => setFolderModalName(e.target.value)}
              placeholder="Nombre de carpeta"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') void createFolderFromModal()
              }}
            />
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-black/15 px-4 py-2 text-sm font-medium hover:bg-black/5"
                onClick={() => setFolderModalOpen(false)}
              >
                Cancelar
              </button>
              <WorkspaceActionButton
                type="button"
                disabled={!folderModalName.trim() || busy}
                onAction={createFolderFromModal}
                successLabel="Carpeta creada"
              >
                Crear
              </WorkspaceActionButton>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  )
}

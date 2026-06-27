import { useCallback, useEffect, useState } from 'react'
import { Upload } from 'lucide-react'

import { apiFetch, apiStatusErrorMessage } from '../../api/client'
import {
  filterAllowedProjectFiles,
  formatAllowedProjectExtensionsHint,
  PROJECT_FILE_ACCEPT_ATTR,
} from '../../constants/projectAllowedFiles'
import { PrimaryButton } from '../PrimaryButton'
import { WorkspaceActionButton } from './WorkspaceActionButton'
import { DuplaLogo } from '../DuplaLogo'
import {
  PROJECT_FILE_DISCIPLINE_LABELS,
  PROJECT_FILE_DISCIPLINE_VALUES,
  type ProjectFileDisciplineValue,
} from '../../constants/projectFileDisciplines'
import type { ProjectFileFolderRow, ProjectFileRow } from '../../types/projectWorkspace'
import {
  BUDGET_EXCLUDED_UPLOAD_NOTICE,
  uploadsExcludedFromBudget,
} from '../../lib/projectFileBudget'
import { ProjectWorkspaceFileIcon } from './ProjectWorkspaceFileIcon'

const UPLOAD_CONCURRENCY = 5

const STEP_META = [
  {
    title: 'Archivos',
    description:
      'Tipos admitidos: planos CAD, PDF, IFC y documentos técnicos .docx. En el siguiente paso se sugiere descripción y disciplina (sin leer el binario de CAD/BIM).',
    footerHint: 'Selección',
  },
  {
    title: 'Revisión',
    description:
      'Revisa la descripción y la disciplina sugeridas. Puedes editarlas antes de publicar.',
    footerHint: 'IA',
  },
  {
    title: 'Ubicación',
    description:
      'Elige la carpeta de destino o crea una nueva. Al confirmar, los archivos quedarán publicados en ese lugar.',
    footerHint: 'Carpeta',
  },
] as const

type DraftEdit = { description: string; discipline: string }

type ProjectFilesUploadWizardProps = {
  open: boolean
  onClose: () => void
  projectUuid: string
  token: string | null
  workflowPhase: string
  /** Carpeta actual del workspace al abrir; los borradores se suben aquí; en el paso 3 puedes cambiar destino. */
  defaultFolderUuid: string | null
  defaultFolderLabel?: string | null
  initialFiles?: File[]
  onCompleted: () => void
}

export function ProjectFilesUploadWizard({
  open,
  onClose,
  projectUuid,
  token,
  workflowPhase,
  defaultFolderUuid,
  defaultFolderLabel,
  initialFiles,
  onCompleted,
}: ProjectFilesUploadWizardProps) {
  const [step, setStep] = useState(1)
  const [picked, setPicked] = useState<File[]>([])
  const [uploaded, setUploaded] = useState<ProjectFileRow[]>([])
  const [edits, setEdits] = useState<Record<string, DraftEdit>>({})
  const [uploadBusy, setUploadBusy] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number } | null>(null)
  const [publishBusy, setPublishBusy] = useState(false)
  const [publishProgress, setPublishProgress] = useState<{ done: number; total: number } | null>(null)

  const [locFolder, setLocFolder] = useState<string | null>(null)
  const [locFolders, setLocFolders] = useState<ProjectFileFolderRow[]>([])
  const [locTrail, setLocTrail] = useState<{ uuid: string | null; name: string }[]>([
    { uuid: null, name: 'Raíz' },
  ])
  const [newFolderName, setNewFolderName] = useState('')
  const [locBusy, setLocBusy] = useState(false)

  const reset = useCallback(() => {
    setStep(1)
    setPicked([])
    setUploaded([])
    setEdits({})
    setUploadBusy(false)
    setUploadError(null)
    setUploadProgress(null)
    setPublishBusy(false)
    setPublishProgress(null)
    setLocFolder(defaultFolderUuid)
    setLocTrail([{ uuid: null, name: 'Raíz' }])
    setNewFolderName('')
  }, [defaultFolderUuid])

  useEffect(() => {
    if (!open) return
    reset()
    if (initialFiles?.length) setPicked(initialFiles)
  }, [open, reset, initialFiles])

  useEffect(() => {
    if (!open) return
    setLocFolder(defaultFolderUuid)
  }, [open, defaultFolderUuid])

  useEffect(() => {
    if (step !== 3) return
    if (defaultFolderUuid) {
      setLocFolder(defaultFolderUuid)
      setLocTrail([
        { uuid: null, name: 'Raíz' },
        { uuid: defaultFolderUuid, name: defaultFolderLabel?.trim() || 'Carpeta actual' },
      ])
    } else {
      setLocFolder(null)
      setLocTrail([{ uuid: null, name: 'Raíz' }])
    }
  }, [step, defaultFolderUuid, defaultFolderLabel])

  const loadLocFolders = useCallback(async () => {
    if (!token || !projectUuid) return
    setLocBusy(true)
    try {
      const q =
        locFolder === null
          ? ''
          : `?parent_uuid=${encodeURIComponent(locFolder)}`
      const res = await apiFetch(`/api/projects/${projectUuid}/file-folders${q}`, { token })
      if (res.ok) setLocFolders((await res.json()) as ProjectFileFolderRow[])
    } finally {
      setLocBusy(false)
    }
  }, [token, projectUuid, locFolder])

  useEffect(() => {
    if (!open || step !== 3) return
    void loadLocFolders()
  }, [open, step, loadLocFolders])

  const stepMeta = STEP_META[step - 1]

  function addPickedFiles(incoming: File[]) {
    const { allowed, rejected } = filterAllowedProjectFiles(incoming)
    if (allowed.length) setPicked((prev) => [...prev, ...allowed])
    if (rejected.length) {
      setUploadError(
        `Solo se admiten ${formatAllowedProjectExtensionsHint()}. Se ignoraron ${rejected.length} archivo(s).`,
      )
    } else if (allowed.length) {
      setUploadError(null)
    }
  }

  const canNextFrom1 = picked.length > 0 && !uploadBusy

  async function runUploads() {
    if (!token || picked.length === 0) return
    setUploadBusy(true)
    setUploadError(null)
    setUploadProgress({ done: 0, total: picked.length })
    const next: ProjectFileRow[] = []
    try {
      for (let i = 0; i < picked.length; i += UPLOAD_CONCURRENCY) {
        const chunk = picked.slice(i, i + UPLOAD_CONCURRENCY)
        const batch = await Promise.all(
          chunk.map(async (file) => {
            const fd = new FormData()
            fd.append('file', file)
            fd.append('wizard', 'true')
            if (defaultFolderUuid) fd.append('folder_uuid', defaultFolderUuid)
            const res = await apiFetch(`/api/projects/${projectUuid}/files`, {
              method: 'POST',
              token,
              body: fd,
            })
            const body = (await res.json().catch(() => ({}))) as ProjectFileRow & { detail?: string }
            if (!res.ok) {
              throw new Error(body.detail ?? apiStatusErrorMessage(res.status))
            }
            return body as ProjectFileRow
          }),
        )
        next.push(...batch)
        setUploadProgress({ done: next.length, total: picked.length })
      }
      setUploaded(next)
      const ed: Record<string, DraftEdit> = {}
      for (const r of next) {
        ed[r.uuid] = {
          description: r.description ?? '',
          discipline: r.discipline ?? '',
        }
      }
      setEdits(ed)
      setStep(2)
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Error al subir archivo')
    } finally {
      setUploadBusy(false)
      setUploadProgress(null)
    }
  }

  async function deleteDrafts(uuids: string[]) {
    if (!token) return
    await Promise.all(
      uuids.map((u) =>
        apiFetch(`/api/projects/${projectUuid}/files/${u}`, { method: 'DELETE', token }),
      ),
    )
  }

  async function handleClose() {
    if (uploaded.some((u) => u.ingest_status === 'DRAFT')) {
      await deleteDrafts(uploaded.filter((u) => u.ingest_status === 'DRAFT').map((u) => u.uuid))
    }
    reset()
    onClose()
  }

  async function createFolderInWizard() {
    if (!token || !newFolderName.trim()) return
    setLocBusy(true)
    try {
      const res = await apiFetch(`/api/projects/${projectUuid}/file-folders`, {
        method: 'POST',
        token,
        body: JSON.stringify({
          name: newFolderName.trim(),
          parent_uuid: locFolder,
        }),
      })
      if (!res.ok) return
      setNewFolderName('')
      await loadLocFolders()
    } finally {
      setLocBusy(false)
    }
  }

  async function confirmPublish(): Promise<boolean> {
    if (!token || uploaded.length === 0) return false
    setPublishBusy(true)
    setUploadError(null)
    setPublishProgress({ done: 0, total: uploaded.length })
    try {
      for (let i = 0; i < uploaded.length; i += UPLOAD_CONCURRENCY) {
        const chunk = uploaded.slice(i, i + UPLOAD_CONCURRENCY)
        await Promise.all(
          chunk.map(async (r) => {
            const e = edits[r.uuid] ?? { description: '', discipline: '' }
            const body: Record<string, unknown> = {
              ingest_status: 'PUBLISHED',
              folder_uuid: locFolder,
              description: e.description.trim() || null,
            }
            const d = e.discipline.trim()
            body.discipline = d ? d : null
            const res = await apiFetch(`/api/projects/${projectUuid}/files/${r.uuid}`, {
              method: 'PATCH',
              token,
              body: JSON.stringify(body),
            })
            if (!res.ok) {
              const err = (await res.json().catch(() => ({}))) as { detail?: string }
              throw new Error(err.detail ?? 'Error al publicar')
            }
          }),
        )
        setPublishProgress({ done: Math.min(i + chunk.length, uploaded.length), total: uploaded.length })
      }
      onCompleted()
      reset()
      onClose()
      return true
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Error al publicar')
      return false
    } finally {
      setPublishBusy(false)
      setPublishProgress(null)
    }
  }

  function goLocInto(folder: ProjectFileFolderRow) {
    setLocFolder(folder.uuid)
    setLocTrail((t) => [...t, { uuid: folder.uuid, name: folder.name }])
  }

  function goLocToIndex(i: number) {
    const slice = locTrail.slice(0, i + 1)
    setLocTrail(slice)
    const last = slice[slice.length - 1]
    setLocFolder(last?.uuid ?? null)
  }

  const maxStep = 3

  const showBudgetExcludedNotice = uploadsExcludedFromBudget(workflowPhase)

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) void handleClose()
      }}
    >
      <div
        className="flex h-[min(90vh,720px)] w-full max-w-5xl min-h-0 flex-col overflow-hidden rounded-xl border border-black/10 bg-white shadow-xl md:flex-row"
        role="dialog"
        aria-labelledby="files-wizard-title"
        aria-modal="true"
      >
        <aside className="flex min-h-0 w-full shrink-0 flex-col border-b border-black/10 bg-gradient-to-br from-primary/[0.08] to-black/[0.02] px-4 py-5 md:w-[220px] md:border-b-0 md:border-r md:py-6">
          <div className="flex justify-center px-2">
            <DuplaLogo className="h-9 w-auto max-w-[min(100%,12rem)] object-contain" />
          </div>
          <div className="mt-4 min-h-0 flex-1 overflow-y-auto">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-primary">Subir archivos</p>
            <h2 id="files-wizard-title" className="mt-1 text-lg font-semibold leading-snug text-ink">
              {stepMeta.title}
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted">{stepMeta.description}</p>
          </div>
          <div className="mt-6 shrink-0 border-t border-black/10 pt-4">
            <div className="flex items-center justify-center gap-1.5" aria-label="Pasos">
              {[1, 2, 3].map((n) => (
                <span key={n} className="flex items-center gap-1.5">
                  {n > 1 ? <span className="h-px w-5 bg-black/15" aria-hidden /> : null}
                  <span
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                      step === n
                        ? 'bg-primary text-white shadow-sm'
                        : step > n
                          ? 'bg-primary/20 text-primary'
                          : 'border border-black/15 bg-white/80 text-muted'
                    }`}
                  >
                    {n}
                  </span>
                </span>
              ))}
            </div>
            <p className="mt-2 text-center text-[11px] text-muted">
              Paso {step} de {maxStep} — {stepMeta.footerHint}
            </p>
          </div>
        </aside>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div
            className={`min-h-0 flex-1 px-6 py-5 md:px-8 ${
              step === 1 ? 'flex flex-col overflow-hidden' : 'overflow-y-auto'
            }`}
          >
            {uploadError ? (
              <p className="mb-3 shrink-0 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                {uploadError}
              </p>
            ) : null}
            {showBudgetExcludedNotice ? (
              <p className="mb-3 shrink-0 rounded-md border border-amber-200/80 bg-amber-50 px-3 py-2 text-sm text-amber-950">
                {BUDGET_EXCLUDED_UPLOAD_NOTICE}
              </p>
            ) : null}

            {step === 1 ? (
              <div className="flex min-h-0 flex-1 flex-col gap-3">
                <label
                  className="flex min-h-0 flex-1 cursor-pointer flex-col rounded-xl border-2 border-dashed border-black/15 bg-black/[0.02] transition-colors hover:border-primary/30 hover:bg-primary/[0.03]"
                  onDragOver={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                  }}
                  onDrop={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    if (e.dataTransfer.files?.length) addPickedFiles(Array.from(e.dataTransfer.files))
                  }}
                >
                  <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 py-6">
                    <Upload className="h-10 w-10 text-primary/80" strokeWidth={1.25} aria-hidden />
                    <span className="text-center text-sm font-medium text-ink">
                      Arrastra archivos aquí o elige desde tu equipo
                    </span>
                  </div>
                  {picked.length > 0 ? (
                    <ul className="max-h-[min(40%,12rem)] shrink-0 space-y-1 overflow-y-auto border-t border-black/5 px-4 py-3 text-sm text-muted">
                      {picked.map((f) => (
                        <li key={`${f.name}-${f.size}`} className="flex items-center gap-2">
                          <ProjectWorkspaceFileIcon name={f.name} className="h-4 w-4 shrink-0 text-primary" />
                          {f.name}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="shrink-0 pb-4 text-center text-xs text-muted">Ningún archivo seleccionado.</p>
                  )}
                  <input
                    type="file"
                    className="sr-only"
                    multiple
                    accept={PROJECT_FILE_ACCEPT_ATTR}
                    onChange={(e) => {
                      const list = e.target.files
                      if (list?.length) addPickedFiles(Array.from(list))
                      e.target.value = ''
                    }}
                  />
                </label>
                {uploadBusy && uploadProgress ? (
                  <p className="shrink-0 text-center text-xs text-muted" aria-live="polite">
                    Subiendo {uploadProgress.done} / {uploadProgress.total}…
                  </p>
                ) : null}
              </div>
            ) : null}

            {step === 2 ? (
              <div className="space-y-4">
                <p className="text-xs text-muted">
                  Sugerencia basada en el nombre del archivo y el tipo; los DWG/DXF no se leen como texto.
                </p>
                {uploaded.map((r) => (
                  <div
                    key={r.uuid}
                    className="rounded-lg border border-black/10 bg-white p-4 shadow-[var(--shadow-card)]"
                  >
                    <div className="flex items-start gap-3">
                      <ProjectWorkspaceFileIcon name={r.original_name} className="h-9 w-9 shrink-0 text-primary" />
                      <div className="min-w-0 flex-1 space-y-2">
                        <p className="truncate text-sm font-medium text-ink">{r.original_name}</p>
                        <label className="block text-xs text-muted">
                          Descripción
                          <textarea
                            className="du-input mt-1 min-h-[72px] w-full resize-y text-sm"
                            value={edits[r.uuid]?.description ?? ''}
                            onChange={(e) =>
                              setEdits((prev) => ({
                                ...prev,
                                [r.uuid]: {
                                  ...prev[r.uuid],
                                  description: e.target.value,
                                  discipline: prev[r.uuid]?.discipline ?? '',
                                },
                              }))
                            }
                          />
                        </label>
                        <label className="block text-xs text-muted">
                          Disciplina
                          <select
                            className="du-input mt-1 w-full text-sm"
                            value={edits[r.uuid]?.discipline ?? ''}
                            onChange={(e) =>
                              setEdits((prev) => ({
                                ...prev,
                                [r.uuid]: {
                                  description: prev[r.uuid]?.description ?? '',
                                  discipline: e.target.value,
                                },
                              }))
                            }
                          >
                            <option value="">Sin clasificar</option>
                            {PROJECT_FILE_DISCIPLINE_VALUES.map((v) => (
                              <option key={v} value={v}>
                                {PROJECT_FILE_DISCIPLINE_LABELS[v as ProjectFileDisciplineValue]}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}

            {step === 3 ? (
              <div className="space-y-4">
                {publishBusy && publishProgress ? (
                  <p className="text-xs text-muted" aria-live="polite">
                    Publicando {publishProgress.done} / {publishProgress.total}…
                  </p>
                ) : null}
                <nav className="flex flex-wrap items-center gap-1 text-xs text-muted" aria-label="Ruta">
                  {locTrail.map((seg, i) => (
                    <span key={`${seg.uuid ?? 'root'}-${i}`} className="flex items-center gap-1">
                      {i > 0 ? <span className="text-black/25">/</span> : null}
                      <button
                        type="button"
                        className={`rounded px-1 py-0.5 hover:bg-black/5 ${
                          i === locTrail.length - 1 ? 'font-semibold text-ink' : 'text-primary'
                        }`}
                        onClick={() => goLocToIndex(i)}
                      >
                        {seg.name}
                      </button>
                    </span>
                  ))}
                </nav>

                <div className="grid gap-2 sm:grid-cols-2">
                  {locFolders.map((f) => (
                    <button
                      key={f.uuid}
                      type="button"
                      className="flex items-center gap-3 rounded-lg border border-black/10 bg-white p-3 text-left text-sm transition-colors hover:border-primary/30"
                      onClick={() => goLocInto(f)}
                    >
                      <ProjectWorkspaceFileIcon isFolder name={f.name} className="h-8 w-8 text-amber-600/90" />
                      <span className="truncate font-medium">{f.name}</span>
                    </button>
                  ))}
                </div>

                <div className="flex flex-wrap items-end gap-2 border-t border-black/10 pt-3">
                  <div className="min-w-[12rem] flex-1">
                    <label className="du-label text-xs">Nueva carpeta aquí</label>
                    <input
                      className="du-input mt-1 w-full text-sm"
                      value={newFolderName}
                      onChange={(e) => setNewFolderName(e.target.value)}
                      placeholder="Nombre"
                    />
                  </div>
                  <button
                    type="button"
                    className="rounded-lg border border-black/15 px-3 py-2 text-sm font-medium hover:bg-black/5"
                    disabled={locBusy || !newFolderName.trim()}
                    onClick={() => void createFolderInWizard()}
                  >
                    Crear
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-black/10 px-6 py-4 md:px-8">
            <button
              type="button"
              className="text-sm font-medium text-muted hover:text-ink"
              onClick={() => {
                if (step === 1) void handleClose()
                else if (step === 2) setStep(1)
                else setStep(2)
              }}
            >
              {step === 1 ? 'Cancelar' : 'Atrás'}
            </button>
            <div className="flex gap-2">
              {step === 1 ? (
                <PrimaryButton
                  type="button"
                  disabled={!canNextFrom1}
                  onClick={() => void runUploads()}
                >
                  {uploadBusy ? `Subiendo${uploadProgress ? ` (${uploadProgress.done}/${uploadProgress.total})` : ''}…` : 'Siguiente'}
                </PrimaryButton>
              ) : null}
              {step === 2 ? (
                <PrimaryButton type="button" onClick={() => setStep(3)}>
                  Siguiente
                </PrimaryButton>
              ) : null}
              {step === 3 ? (
                <WorkspaceActionButton
                  type="button"
                  disabled={publishBusy}
                  onAction={confirmPublish}
                  successLabel="Publicado"
                  runningLabel={
                    publishBusy && publishProgress
                      ? `Publicando (${publishProgress.done}/${publishProgress.total})…`
                      : 'Publicando…'
                  }
                >
                  Publicar
                </WorkspaceActionButton>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

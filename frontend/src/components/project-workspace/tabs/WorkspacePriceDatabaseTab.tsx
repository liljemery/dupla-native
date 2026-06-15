import { useCallback, useEffect, useState } from 'react'
import { FileSpreadsheet, FileText, Package, Trash2, Upload, Users } from 'lucide-react'

import { apiFetch } from '../../../api/client'
import { confirmDestructive } from '../../../lib/duplaAlert'
import { WorkspaceActionButton } from '../WorkspaceActionButton'

export type PriceDatabaseFileRow = {
  file_uuid: string
  original_name: string
  mime: string | null
  file_size_bytes: number | null
  status: string
  price_category: string | null
  is_active: boolean
  error_message: string | null
  created_at: string
}

const ACCEPT = '.pdf,.xlsx,.xls,.csv,'

const CATEGORY_CARDS = [
  {
    key: 'materiales',
    title: 'Materiales',
    body: 'Precios unitarios de insumos, herramientas y equipos.',
    Icon: Package,
  },
  {
    key: 'mano_obra',
    title: 'Mano de obra',
    body: 'Tabuladores de salarios, prestaciones y horas extras vigentes.',
    Icon: Users,
  },
  {
    key: 'subcontratos',
    title: 'Subcontratos',
    body: 'Cotizaciones de servicios externos y especialistas técnicos.',
    Icon: FileText,
  },
] as const

const PRICE_CATEGORY_LABELS: Record<string, string> = {
  materiales: 'Materiales',
  mano_obra: 'Mano de obra',
  subcontratos: 'Subcontratos',
}

function formatBytes(n: number | null | undefined): string {
  if (n == null || n < 0) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function formatRelative(iso: string): string {
  try {
    const d = new Date(iso)
    const diff = Date.now() - d.getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 2) return 'Hace un momento'
    if (mins < 60) return `Hace ${mins} min`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `Hace ${hours} h`
    return d.toLocaleDateString('es-DO', { dateStyle: 'medium' })
  } catch {
    return iso
  }
}

function statusBadge(status: string) {
  const s = status.toLowerCase()
  if (s === 'processing')
    return 'bg-amber-100 text-amber-900 ring-1 ring-amber-200'
  if (s === 'processed') return 'bg-emerald-100 text-emerald-900 ring-1 ring-emerald-200'
  return 'bg-red-100 text-red-900 ring-1 ring-red-200'
}

function statusLabel(status: string) {
  const s = status.toLowerCase()
  if (s === 'processing') return 'Procesando'
  if (s === 'processed') return 'Procesado'
  return 'Error'
}

type WorkspacePriceDatabaseTabProps = {
  projectUuid: string
  token: string | null
  flowMsg: string | null
}

export function WorkspacePriceDatabaseTab({ projectUuid, token, flowMsg }: WorkspacePriceDatabaseTabProps) {
  const [items, setItems] = useState<PriceDatabaseFileRow[]>([])
  const [uploadBusy, setUploadBusy] = useState(false)
  const [applyBusy, setApplyBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [dropOn, setDropOn] = useState(false)

  const load = useCallback(async () => {
    if (!token || !projectUuid) return
    const res = await apiFetch(`/api/projects/${projectUuid}/price-database/files`, { token })
    if (!res.ok) return
    const j = (await res.json()) as { items: PriceDatabaseFileRow[] }
    setItems(Array.isArray(j.items) ? j.items : [])
  }, [token, projectUuid])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const needsPoll = items.some((i) => i.status.toLowerCase() === 'processing')
    if (!needsPoll || !token || !projectUuid) return
    const t = window.setInterval(() => void load(), 2800)
    return () => window.clearInterval(t)
  }, [items, load, token, projectUuid])

  async function uploadFiles(files: FileList | File[]) {
    if (!token || !projectUuid) return
    const list = Array.from(files)
    if (!list.length) return
    setUploadBusy(true)
    setMsg(null)
    try {
      for (const file of list) {
        const fd = new FormData()
        fd.append('file', file)
        const res = await apiFetch(`/api/projects/${projectUuid}/price-database/files`, {
          method: 'POST',
          token,
          body: fd,
        })
        const j = await res.json().catch(() => ({}))
        if (!res.ok) {
          setMsg((j as { detail?: string }).detail ?? 'No se pudo subir el archivo')
          break
        }
      }
      await load()
    } finally {
      setUploadBusy(false)
    }
  }

  async function removeFile(fileUuid: string) {
    if (!token || !projectUuid) return
    if (
      !(await confirmDestructive({
        title: '¿Eliminar este archivo de la base de precios?',
      }))
    ) {
      return
    }
    const res = await apiFetch(`/api/projects/${projectUuid}/price-database/files/${fileUuid}`, {
      method: 'DELETE',
      token,
    })
    if (!res.ok) {
      setMsg('No se pudo eliminar')
      return
    }
    await load()
  }

  async function applyDatabase(): Promise<boolean> {
    if (!token || !projectUuid) return false
    setApplyBusy(true)
    setMsg(null)
    try {
      const res = await apiFetch(`/api/projects/${projectUuid}/price-database/apply`, {
        method: 'POST',
        token,
        body: JSON.stringify({}),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) {
        setMsg((j as { detail?: string }).detail ?? 'No se pudo confirmar')
        return false
      }
      setMsg('Base de precios confirmada para presupuestos activos.')
      return true
    } finally {
      setApplyBusy(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-auto">
      {flowMsg ? <p className="text-sm text-amber-800">{flowMsg}</p> : null}
      {msg ? <p className="text-sm text-ink">{msg}</p> : null}

      <div className="rounded-2xl border border-primary/15 bg-[#faf6f4] p-5 shadow-sm sm:p-7">
        <header className="max-w-3xl">
          <h2 className="text-xl font-bold tracking-tight text-ink sm:text-2xl">Base de datos de precios</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted sm:text-base">
            Puedes subir archivos de precios o cotizaciones (PDF o Excel/CSV). La inteligencia artificial los clasifica
            en <strong className="text-ink">materiales</strong>, <strong className="text-ink">mano de obra</strong> o{' '}
            <strong className="text-ink">subcontratos</strong>. Si subes uno nuevo del mismo tipo, el anterior queda
            inactivo y el nuevo pasa a ser la referencia.
          </p>
        </header>

        <p className="mt-8 text-xs font-bold uppercase tracking-[0.14em] text-primary/90">Qué puedes subir</p>
        <ul className="mt-3 grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-3">
          {CATEGORY_CARDS.map(({ key, title, body, Icon }) => (
            <li
              key={key}
              className="rounded-xl border-2 border-primary/20 bg-white p-4 shadow-[0_1px_0_rgba(193,13,18,0.05)]"
            >
              <div className="flex items-start gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon className="h-5 w-5" aria-hidden />
                </span>
                <div>
                  <h3 className="font-bold text-ink">{title}</h3>
                  <p className="mt-1 text-sm leading-snug text-muted">{body}</p>
                </div>
              </div>
            </li>
          ))}
        </ul>

        <div className="mt-8">
          <label
            className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-12 transition-colors sm:py-14 ${
              dropOn ? 'border-primary bg-primary/6' : 'border-primary/40 bg-white/80 hover:border-primary/60'
            }`}
            onDragOver={(e) => {
              e.preventDefault()
              setDropOn(true)
            }}
            onDragLeave={() => setDropOn(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDropOn(false)
              if (e.dataTransfer.files?.length) void uploadFiles(e.dataTransfer.files)
            }}
          >
            <Upload className="h-10 w-10 text-primary/80" strokeWidth={1.5} aria-hidden />
            <span className="mt-3 text-base font-semibold text-ink">Arrastra tus archivos aquí</span>
            <span className="mt-1 text-sm text-muted">o elige archivos desde tu equipo</span>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {['XLS', 'XLSX', 'CSV', 'PDF'].map((ext) => (
                <span
                  key={ext}
                  className="rounded-md border border-black/10 bg-white px-2.5 py-1 text-xs font-semibold text-muted"
                >
                  {ext}
                </span>
              ))}
            </div>
            <input
              type="file"
              className="sr-only"
              accept={ACCEPT}
              multiple
              disabled={uploadBusy || !token}
              onChange={(e) => {
                const f = e.target.files
                e.target.value = ''
                if (f?.length) void uploadFiles(f)
              }}
            />
          </label>
        </div>

        <section className="mt-10" aria-labelledby="recent-pdb-heading">
          <h3 id="recent-pdb-heading" className="text-xs font-bold uppercase tracking-[0.14em] text-primary/90">
            Archivos recientes
          </h3>
          <div className="mt-3 overflow-hidden rounded-xl border-2 border-primary/15 bg-white">
            <table className="w-full min-w-[640px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-black/10 bg-black/2 text-xs font-semibold uppercase tracking-wide text-muted">
                  <th className="px-4 py-3">Archivo</th>
                  <th className="px-4 py-3">Categoría</th>
                  <th className="px-4 py-3">Estado</th>
                  <th className="w-12 px-2 py-3" />
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-10 text-center text-muted">
                      Todavía no hay archivos. Sube un PDF o Excel para comenzar.
                    </td>
                  </tr>
                ) : (
                  items.map((row) => (
                    <tr key={row.file_uuid} className="border-b border-black/8 last:border-0">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <FileSpreadsheet className="h-4 w-4 shrink-0 text-muted" aria-hidden />
                          <div className="min-w-0">
                            <div className="truncate font-medium text-ink">{row.original_name}</div>
                            <div className="text-xs text-muted">
                              {formatBytes(row.file_size_bytes)} · {formatRelative(row.created_at)}
                              {row.is_active ? (
                                <span className="ml-2 font-semibold text-primary"> · Activo</span>
                              ) : null}
                            </div>
                            {row.error_message ? (
                              <div className="mt-1 text-xs text-red-700">{row.error_message}</div>
                            ) : null}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted">
                        {row.price_category
                          ? PRICE_CATEGORY_LABELS[row.price_category] ?? row.price_category
                          : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-bold uppercase ${statusBadge(row.status)}`}
                        >
                          {statusLabel(row.status)}
                        </span>
                      </td>
                      <td className="px-2 py-3">
                        <button
                          type="button"
                          className="rounded-md p-2 text-muted hover:bg-red-50 hover:text-red-700"
                          title="Eliminar"
                          onClick={() => void removeFile(row.file_uuid)}
                        >
                          <Trash2 className="h-4 w-4" aria-hidden />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        <div className="du-callout mt-8 border-2 border-primary/25 bg-primary/4 text-sm leading-relaxed">
          <strong className="text-ink">Nota importante:</strong> la actualización de la base de datos impacta en los
          presupuestos que usen estos ítems. Revisa los archivos antes de una carga masiva. El botón inferior confirma
          que los <strong className="text-ink">archivos activos</strong> por categoría son los que quieres usar como
          referencia.
        </div>

        <div className="mt-8 flex justify-center">
          <WorkspaceActionButton
            type="button"
            className="min-w-[240px] px-8 py-3 text-base"
            disabled={applyBusy}
            onAction={applyDatabase}
            successLabel="Base actualizada"
            runningLabel="Aplicando…"
          >
            Actualizar base de datos
          </WorkspaceActionButton>
        </div>
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { ChevronDown, ChevronUp, Plus, Trash2 } from 'lucide-react'

import { apiFetch } from '../api/client'
import { PrimaryButton } from './PrimaryButton'
import type { TaskListDto } from '../types/taskBoard'

type Props = {
  token: string
  lists: TaskListDto[]
  onClose: () => void
  onChanged: () => void
}

type RowState = { uuid: string; title: string }

export function TaskboardSettingsModal({ token, lists, onClose, onChanged }: Props) {
  const [rows, setRows] = useState<RowState[]>(() =>
    [...lists].sort((a, b) => a.position - b.position).map((l) => ({ uuid: l.uuid, title: l.title })),
  )
  const [newTitle, setNewTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setRows([...lists].sort((a, b) => a.position - b.position).map((l) => ({ uuid: l.uuid, title: l.title })))
  }, [lists])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function persistOrder(next: RowState[]) {
    setBusy(true)
    setError(null)
    try {
      const res = await apiFetch('/api/tasks/lists/order', {
        method: 'PUT',
        token,
        body: JSON.stringify({ list_uuids: next.map((r) => r.uuid) }),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setError((j as { detail?: string }).detail ?? 'No se pudo reordenar')
        return
      }
      setRows(next)
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  function moveRow(index: number, delta: -1 | 1) {
    const next = [...rows]
    const target = index + delta
    if (target < 0 || target >= next.length) return
    const tmp = next[index]!
    next[index] = next[target]!
    next[target] = tmp
    setRows(next)
    void persistOrder(next)
  }

  async function saveTitle(uuid: string, title: string) {
    const trimmed = title.trim()
    const original = lists.find((l) => l.uuid === uuid)?.title ?? ''
    if (!trimmed || trimmed === original) return
    setBusy(true)
    setError(null)
    try {
      const res = await apiFetch(`/api/tasks/lists/${uuid}`, {
        method: 'PATCH',
        token,
        body: JSON.stringify({ title: trimmed }),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setError((j as { detail?: string }).detail ?? 'No se pudo renombrar')
        return
      }
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  async function addColumn() {
    const title = newTitle.trim()
    if (!title) return
    setBusy(true)
    setError(null)
    try {
      const res = await apiFetch('/api/tasks/lists', {
        method: 'POST',
        token,
        body: JSON.stringify({ title }),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setError((j as { detail?: string }).detail ?? 'No se pudo crear la columna')
        return
      }
      setNewTitle('')
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  async function deleteColumn(uuid: string) {
    setBusy(true)
    setError(null)
    try {
      const res = await apiFetch(`/api/tasks/lists/${uuid}`, { method: 'DELETE', token })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setError((j as { detail?: string }).detail ?? 'No se pudo eliminar')
        return
      }
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-lg border border-black/10 bg-white shadow-lg"
        role="dialog"
        aria-labelledby="taskboard-settings-title"
        aria-modal="true"
      >
        <div className="border-b border-black/10 px-6 py-4">
          <h2 id="taskboard-settings-title" className="text-lg font-semibold text-ink">
            Configurar tablero
          </h2>
          <p className="mt-1 text-sm text-muted">Añade columnas, renómbralas o cambia su orden.</p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          <ul className="space-y-2">
            {rows.map((row, index) => (
              <li
                key={row.uuid}
                className="flex items-center gap-2 rounded-md border border-black/10 bg-white px-2 py-2"
              >
                <div className="flex shrink-0 flex-col">
                  <button
                    type="button"
                    className="rounded p-0.5 text-muted hover:bg-black/5 hover:text-ink disabled:opacity-30"
                    disabled={busy || index === 0}
                    aria-label="Subir columna"
                    onClick={() => moveRow(index, -1)}
                  >
                    <ChevronUp className="size-4" aria-hidden />
                  </button>
                  <button
                    type="button"
                    className="rounded p-0.5 text-muted hover:bg-black/5 hover:text-ink disabled:opacity-30"
                    disabled={busy || index === rows.length - 1}
                    aria-label="Bajar columna"
                    onClick={() => moveRow(index, 1)}
                  >
                    <ChevronDown className="size-4" aria-hidden />
                  </button>
                </div>
                <input
                  className="du-input min-w-0 flex-1 text-sm"
                  value={row.title}
                  disabled={busy}
                  maxLength={120}
                  onChange={(e) =>
                    setRows((prev) =>
                      prev.map((r) => (r.uuid === row.uuid ? { ...r, title: e.target.value } : r)),
                    )
                  }
                  onBlur={() => void saveTitle(row.uuid, row.title)}
                />
                <button
                  type="button"
                  className="shrink-0 rounded p-2 text-muted hover:bg-primary/10 hover:text-primary disabled:opacity-30"
                  disabled={busy || rows.length <= 1}
                  aria-label="Eliminar columna"
                  title="Solo columnas vacías"
                  onClick={() => void deleteColumn(row.uuid)}
                >
                  <Trash2 className="size-4" aria-hidden />
                </button>
              </li>
            ))}
          </ul>

          <div className="mt-4 flex gap-2">
            <input
              className="du-input min-w-0 flex-1 text-sm"
              placeholder="Nueva columna…"
              value={newTitle}
              disabled={busy}
              maxLength={120}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void addColumn()
              }}
            />
            <PrimaryButton
              type="button"
              className="shrink-0 gap-1 px-3 py-2 text-xs"
              disabled={busy || !newTitle.trim()}
              onClick={() => void addColumn()}
            >
              <Plus className="size-3.5" aria-hidden />
              Añadir
            </PrimaryButton>
          </div>

          {error ? <p className="mt-3 text-sm text-primary">{error}</p> : null}
        </div>

        <div className="flex justify-end border-t border-black/10 px-6 py-4">
          <button
            type="button"
            className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink"
            onClick={onClose}
          >
            Cerrar
          </button>
        </div>
      </div>
    </div>
  )
}

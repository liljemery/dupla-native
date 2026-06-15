import { useEffect, useState } from 'react'

import { apiFetch } from '../api/client'
import { formatPersonFullName } from '../lib/personDisplay'
import { PrimaryButton } from './PrimaryButton'
import type { TaskAssigneeOption } from '../types/taskBoard'

type ListOption = { uuid: string; title: string }

type Props = {
  token: string
  lists: ListOption[]
  assignees: TaskAssigneeOption[]
  defaultProjectUuid?: string
  onClose: () => void
  onCreated: () => void
}

export function TaskboardCreateModal({
  token,
  lists,
  assignees,
  defaultProjectUuid,
  onClose,
  onCreated,
}: Props) {
  const defaultList = lists[0]?.uuid ?? ''
  const [listUuid, setListUuid] = useState(defaultList)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [assigneeUuid, setAssigneeUuid] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (lists[0]?.uuid) {
      setListUuid((prev) => (lists.some((l) => l.uuid === prev) ? prev : lists[0].uuid))
    }
  }, [lists])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function submit() {
    const t = title.trim()
    if (!t || !listUuid) return
    setError(null)
    setSaving(true)
    try {
      const res = await apiFetch('/api/tasks/cards', {
        method: 'POST',
        token,
        body: JSON.stringify({
          list_uuid: listUuid,
          title: t,
          description: description.trim() || null,
          assignee_uuid: assigneeUuid || null,
          project_uuid: defaultProjectUuid ?? null,
        }),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setError((j as { detail?: string }).detail ?? 'No se pudo crear la tarea')
        return
      }
      onCreated()
      onClose()
    } finally {
      setSaving(false)
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
        className="w-full max-w-lg rounded-lg border border-black/10 bg-white p-6 shadow-lg"
        role="dialog"
        aria-labelledby="create-task-title"
        aria-modal="true"
      >
        <h2 id="create-task-title" className="text-lg font-semibold text-ink">
          Nueva tarea
        </h2>

        <div className="mt-4 space-y-4">
          <div>
            <label className="du-label" htmlFor="ct-list">
              Columna
            </label>
            <select
              id="ct-list"
              className="du-input mt-1"
              value={listUuid}
              onChange={(e) => setListUuid(e.target.value)}
            >
              {lists.map((l) => (
                <option key={l.uuid} value={l.uuid}>
                  {l.title}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="du-label" htmlFor="ct-title">
              Título
            </label>
            <input
              id="ct-title"
              className="du-input mt-1"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={255}
              autoFocus
            />
          </div>
          <div>
            <label className="du-label" htmlFor="ct-desc">
              Descripción breve (opcional)
            </label>
            <textarea
              id="ct-desc"
              className="du-input mt-1 min-h-[72px] resize-y text-sm"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={500}
              rows={3}
            />
            <p className="du-meta mt-0.5">{description.length}/500</p>
          </div>
          <div>
            <label className="du-label" htmlFor="ct-assignee">
              Asignado a
            </label>
            <select
              id="ct-assignee"
              className="du-input mt-1"
              value={assigneeUuid}
              onChange={(e) => setAssigneeUuid(e.target.value)}
            >
              <option value="">Sin asignar</option>
              {assignees.map((a) => (
                <option key={a.uuid} value={a.uuid}>
                  {formatPersonFullName(a.first_name, a.last_name, a.email)}
                </option>
              ))}
            </select>
          </div>
          {error ? <p className="text-sm text-primary">{error}</p> : null}
        </div>

        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink"
            onClick={onClose}
          >
            Cancelar
          </button>
          <PrimaryButton type="button" disabled={saving || !title.trim() || !listUuid} onClick={() => void submit()}>
            {saving ? 'Creando…' : 'Crear tarea'}
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}

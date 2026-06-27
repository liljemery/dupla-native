import { useEffect, useState } from 'react'

import { apiFetch } from '../api/client'
import { WORKFLOW_PHASE_LABELS } from '../constants/workflowPhases'
import { formatPersonFullName } from '../lib/personDisplay'
import { confirmDestructive } from '../lib/duplaAlert'
import { PrimaryButton } from './PrimaryButton'
import type { TaskAssigneeOption, TaskCardCommentDto, TaskCardDto } from '../types/taskBoard'

type Props = {
  token: string
  card: TaskCardDto
  assignees: TaskAssigneeOption[]
  readOnly: boolean
  onClose: () => void
  onSaved: () => void
}

export function TaskboardCardModal({ token, card, assignees, readOnly, onClose, onSaved }: Props) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(card.title)
  const [description, setDescription] = useState(card.description ?? '')
  const [assigneeUuid, setAssigneeUuid] = useState<string>(card.assignee_uuid ?? '')
  const [archived, setArchived] = useState(card.archived)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [comments, setComments] = useState<TaskCardCommentDto[]>([])
  const [commentsLoading, setCommentsLoading] = useState(false)
  const [commentBody, setCommentBody] = useState('')
  const [commentPosting, setCommentPosting] = useState(false)
  const [commentError, setCommentError] = useState<string | null>(null)
  const [archiving, setArchiving] = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    setEditing(false)
    setTitle(card.title)
    setDescription(card.description ?? '')
    setAssigneeUuid(card.assignee_uuid ?? '')
    setArchived(card.archived)
    setError(null)
    setCommentBody('')
    setCommentError(null)
  }, [card])

  useEffect(() => {
    if (!token) return
    let cancelled = false
    async function loadComments() {
      setCommentsLoading(true)
      const res = await apiFetch(`/api/tasks/cards/${card.uuid}/comments`, { token })
      if (!res.ok || cancelled) {
        setCommentsLoading(false)
        return
      }
      setComments((await res.json()) as TaskCardCommentDto[])
      setCommentsLoading(false)
    }
    void loadComments()
    return () => {
      cancelled = true
    }
  }, [token, card.uuid])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function save() {
    if (readOnly) return
    setError(null)
    setSaving(true)
    try {
      const body: Record<string, unknown> = {
        title: title.trim(),
        description: description.trim() || null,
        assignee_uuid: assigneeUuid || null,
        archived,
      }
      const res = await apiFetch(`/api/tasks/cards/${card.uuid}`, {
        method: 'PATCH',
        token,
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setError((j as { detail?: string }).detail ?? 'No se pudo guardar')
        return
      }
      onSaved()
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  function cancelEdit() {
    setTitle(card.title)
    setDescription(card.description ?? '')
    setAssigneeUuid(card.assignee_uuid ?? '')
    setArchived(card.archived)
    setError(null)
    setEditing(false)
  }

  const assigneeFromList = assignees.find((a) => a.uuid === card.assignee_uuid)
  const assigneeLabel = card.assignee_email
    ? formatPersonFullName(card.assignee_first_name, card.assignee_last_name, card.assignee_email)
    : assigneeFromList
      ? formatPersonFullName(assigneeFromList.first_name, assigneeFromList.last_name, assigneeFromList.email)
      : 'Sin asignar'

  async function archiveFromView() {
    if (readOnly || card.archived) return
    setError(null)
    setArchiving(true)
    try {
      const res = await apiFetch(`/api/tasks/cards/${card.uuid}`, {
        method: 'PATCH',
        token,
        body: JSON.stringify({ archived: true }),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setError((j as { detail?: string }).detail ?? 'No se pudo archivar')
        return
      }
      onSaved()
      onClose()
    } finally {
      setArchiving(false)
    }
  }

  async function deletePermanently() {
    if (readOnly) return
    if (
      !(await confirmDestructive({
        title: '¿Eliminar esta tarea de forma permanente?',
        text: 'No se puede deshacer.',
      }))
    ) {
      return
    }
    setError(null)
    setDeleting(true)
    try {
      const res = await apiFetch(`/api/tasks/cards/${card.uuid}`, {
        method: 'DELETE',
        token,
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setError((j as { detail?: string }).detail ?? 'No se pudo eliminar')
        return
      }
      onSaved()
      onClose()
    } finally {
      setDeleting(false)
    }
  }

  async function postComment() {
    const text = commentBody.trim()
    if (!token || !text || readOnly) return
    setCommentError(null)
    setCommentPosting(true)
    try {
      const res = await apiFetch(`/api/tasks/cards/${card.uuid}/comments`, {
        method: 'POST',
        token,
        body: JSON.stringify({ body: text }),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setCommentError((j as { detail?: string }).detail ?? 'No se pudo publicar')
        return
      }
      const row = (await res.json()) as TaskCardCommentDto
      setComments((prev) => [...prev, row])
      setCommentBody('')
    } finally {
      setCommentPosting(false)
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
        aria-labelledby="task-modal-title"
        aria-modal="true"
      >
        <div className="min-h-0 flex-1 overflow-y-scroll px-6 pb-6 pt-6 [-webkit-overflow-scrolling:touch]">
          <h2 id="task-modal-title" className="sr-only">
            Tarea
          </h2>
          {readOnly ? (
            <p className="du-meta">Solo lectura (administrador).</p>
          ) : null}

          <div className="mt-4 space-y-4">
          {!editing ? (
            <>
              <div>
                <h3 className="text-lg font-semibold leading-snug text-ink">{card.title}</h3>
              </div>
              <div>
                <div className="du-label">Descripción</div>
                {card.description?.trim() ? (
                  <p className="mt-1 whitespace-pre-wrap wrap-break-word text-sm text-ink">{card.description}</p>
                ) : (
                  <p className="mt-1 text-sm text-muted">Sin descripción.</p>
                )}
              </div>
              <div>
                <div className="du-label">Asignado a</div>
                <p className="mt-1 text-sm text-ink">{assigneeLabel}</p>
              </div>
              {card.created_in_phase ? (
                <div>
                  <div className="du-label">Fase al crear la tarea</div>
                  <p className="mt-1 text-sm text-ink">
                    {WORKFLOW_PHASE_LABELS[card.created_in_phase] ?? card.created_in_phase}
                  </p>
                </div>
              ) : null}
              <div className="rounded-md border border-black/10 bg-black/2 px-3 py-2 text-sm">
                <div className="du-meta">Creada por</div>
                <div className="text-ink">
                  {card.creator_email
                    ? formatPersonFullName(card.creator_first_name, card.creator_last_name, card.creator_email)
                    : '—'}
                </div>
                <div className="du-meta mt-2">Creada</div>
                <div className="text-muted">
                  {new Date(card.created_at).toLocaleString(undefined, {
                    dateStyle: 'medium',
                    timeStyle: 'short',
                  })}
                </div>
              </div>
              {card.archived ? (
                <p className="text-sm text-muted">Archivada (no aparece en el tablero activo).</p>
              ) : null}
              <div className="border-t border-black/10 pt-4">
                <div className="du-label">Comentarios</div>
                {commentsLoading ? (
                  <p className="mt-2 text-sm text-muted">Cargando…</p>
                ) : comments.length === 0 ? (
                  <p className="mt-2 text-sm text-muted">Aún no hay comentarios.</p>
                ) : (
                  <ul className="mt-2 max-h-48 space-y-3 overflow-y-auto text-sm">
                    {comments.map((c) => (
                      <li key={c.uuid} className="rounded-md border border-black/8 bg-black/2 px-3 py-2">
                        <div className="du-meta flex flex-wrap justify-between gap-2">
                          <span className="text-ink">
                            {c.author_email
                              ? formatPersonFullName(c.author_first_name, c.author_last_name, c.author_email)
                              : '—'}
                          </span>
                          <time className="shrink-0" dateTime={c.created_at}>
                            {new Date(c.created_at).toLocaleString(undefined, {
                              dateStyle: 'short',
                              timeStyle: 'short',
                            })}
                          </time>
                        </div>
                        <p className="mt-1 whitespace-pre-wrap text-ink">{c.body}</p>
                      </li>
                    ))}
                  </ul>
                )}
                {!readOnly ? (
                  <div className="mt-3">
                    <label className="du-label" htmlFor="task-comment">
                      Nuevo comentario
                    </label>
                    <textarea
                      id="task-comment"
                      className="du-input mt-1 min-h-[72px] resize-y text-sm"
                      value={commentBody}
                      onChange={(e) => setCommentBody(e.target.value)}
                      maxLength={2000}
                      rows={3}
                      placeholder="Escribe un comentario…"
                    />
                    {commentError ? <p className="mt-1 text-sm text-primary">{commentError}</p> : null}
                    <PrimaryButton
                      type="button"
                      className="mt-2"
                      disabled={commentPosting || !commentBody.trim()}
                      onClick={() => void postComment()}
                    >
                      {commentPosting ? 'Publicando…' : 'Publicar comentario'}
                    </PrimaryButton>
                  </div>
                ) : null}
              </div>
            </>
          ) : (
            <>
              <div>
                <label className="du-label" htmlFor="tm-title">
                  Título
                </label>
                <input
                  id="tm-title"
                  className="du-input mt-1"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  disabled={readOnly}
                  maxLength={255}
                />
              </div>
              <div>
                <label className="du-label" htmlFor="tm-desc">
                  Descripción breve
                </label>
                <textarea
                  id="tm-desc"
                  className="du-input mt-1 min-h-[72px] resize-y text-sm"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={readOnly}
                  maxLength={500}
                  rows={3}
                />
                <p className="du-meta mt-0.5">{description.length}/500</p>
              </div>
              <div>
                <label className="du-label" htmlFor="tm-assignee">
                  Asignado a
                </label>
                <select
                  id="tm-assignee"
                  className="du-input mt-1"
                  value={assigneeUuid}
                  onChange={(e) => setAssigneeUuid(e.target.value)}
                  disabled={readOnly}
                >
                  <option value="">Sin asignar</option>
                  {assignees.map((a) => (
                    <option key={a.uuid} value={a.uuid}>
                      {formatPersonFullName(a.first_name, a.last_name, a.email)}
                    </option>
                  ))}
                </select>
              </div>
              {card.created_in_phase ? (
                <div className="rounded-md border border-black/10 bg-black/2 px-3 py-2 text-sm">
                  <div className="du-meta">Fase al crear la tarea</div>
                  <div className="text-ink">
                    {WORKFLOW_PHASE_LABELS[card.created_in_phase] ?? card.created_in_phase}
                  </div>
                </div>
              ) : null}
              <div className="rounded-md border border-black/10 bg-black/2 px-3 py-2 text-sm">
                <div className="du-meta">Creada por</div>
                <div className="text-ink">
                  {card.creator_email
                    ? formatPersonFullName(card.creator_first_name, card.creator_last_name, card.creator_email)
                    : '—'}
                </div>
                <div className="du-meta mt-2">Creada</div>
                <div className="text-muted">
                  {new Date(card.created_at).toLocaleString(undefined, {
                    dateStyle: 'medium',
                    timeStyle: 'short',
                  })}
                </div>
              </div>
              {!readOnly ? (
                <label className="flex items-center gap-2 text-sm text-ink">
                  <input
                    type="checkbox"
                    className="rounded border-black/20"
                    checked={archived}
                    onChange={(e) => setArchived(e.target.checked)}
                  />
                  Archivada (sale del tablero activo)
                </label>
              ) : card.archived ? (
                <p className="text-sm text-muted">Esta tarea está archivada.</p>
              ) : null}
              <div className="border-t border-black/10 pt-4">
                <div className="du-label">Comentarios</div>
                {commentsLoading ? (
                  <p className="mt-2 text-sm text-muted">Cargando…</p>
                ) : comments.length === 0 ? (
                  <p className="mt-2 text-sm text-muted">Aún no hay comentarios.</p>
                ) : (
                  <ul className="mt-2 max-h-48 space-y-3 overflow-y-auto text-sm">
                    {comments.map((c) => (
                      <li key={c.uuid} className="rounded-md border border-black/8 bg-black/2 px-3 py-2">
                        <div className="du-meta flex flex-wrap justify-between gap-2">
                          <span className="text-ink">
                            {c.author_email
                              ? formatPersonFullName(c.author_first_name, c.author_last_name, c.author_email)
                              : '—'}
                          </span>
                          <time className="shrink-0" dateTime={c.created_at}>
                            {new Date(c.created_at).toLocaleString(undefined, {
                              dateStyle: 'short',
                              timeStyle: 'short',
                            })}
                          </time>
                        </div>
                        <p className="mt-1 whitespace-pre-wrap text-ink">{c.body}</p>
                      </li>
                    ))}
                  </ul>
                )}
                {!readOnly ? (
                  <div className="mt-3">
                    <label className="du-label" htmlFor="task-comment-edit">
                      Nuevo comentario
                    </label>
                    <textarea
                      id="task-comment-edit"
                      className="du-input mt-1 min-h-[72px] resize-y text-sm"
                      value={commentBody}
                      onChange={(e) => setCommentBody(e.target.value)}
                      maxLength={2000}
                      rows={3}
                    />
                    {commentError ? <p className="mt-1 text-sm text-primary">{commentError}</p> : null}
                    <PrimaryButton
                      type="button"
                      className="mt-2"
                      disabled={commentPosting || !commentBody.trim()}
                      onClick={() => void postComment()}
                    >
                      {commentPosting ? 'Publicando…' : 'Publicar comentario'}
                    </PrimaryButton>
                  </div>
                ) : null}
              </div>
            </>
          )}
            {error ? <p className="text-sm text-primary">{error}</p> : null}
          </div>
        </div>

        <div
          className={`flex shrink-0 flex-wrap items-center gap-3 border-t border-black/10 bg-white px-6 py-4 ${readOnly ? 'justify-end' : 'justify-between'}`}
        >
          {!readOnly ? (
            <div className="flex min-w-0 flex-wrap gap-2">
              {!editing && !card.archived ? (
                <button
                  type="button"
                  className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm text-ink hover:bg-black/4 disabled:opacity-50"
                  disabled={archiving || deleting}
                  onClick={() => void archiveFromView()}
                >
                  {archiving ? 'Archivando…' : 'Archivar'}
                </button>
              ) : null}
              <button
                type="button"
                className="rounded-md border border-primary/30 bg-primary/6 px-3 py-2 text-sm font-medium text-primary hover:bg-primary/10 disabled:opacity-50"
                disabled={archiving || deleting || saving}
                onClick={() => void deletePermanently()}
              >
                {deleting ? 'Eliminando…' : 'Eliminar'}
              </button>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {!editing ? (
              <>
                <button
                  type="button"
                  className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink"
                  onClick={onClose}
                >
                  Cerrar
                </button>
                {!readOnly ? (
                  <PrimaryButton type="button" onClick={() => setEditing(true)}>
                    Editar
                  </PrimaryButton>
                ) : null}
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink"
                  onClick={cancelEdit}
                  disabled={saving || deleting || archiving}
                >
                  Cancelar
                </button>
                {!readOnly ? (
                  <PrimaryButton
                    type="button"
                    disabled={saving || deleting || archiving || !title.trim()}
                    onClick={() => void save()}
                  >
                    {saving ? 'Guardando…' : 'Guardar'}
                  </PrimaryButton>
                ) : null}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

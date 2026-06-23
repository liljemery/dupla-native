import { useState } from 'react'

import { apiFetch } from '../../api/client'
import { PrimaryButton } from '../PrimaryButton'

export type RoleDraft = {
  uuid: string
  name: string
  slug: string
  is_system: boolean
}

type Props = {
  token: string
  open: boolean
  mode: 'create' | 'edit'
  role: RoleDraft | null
  onClose: () => void
  onSaved: () => void
}

export function AdminRoleModal({ token, open, mode, role, onClose, onSaved }: Props) {
  if (!open) return null

  return (
    <AdminRoleModalForm
      key={`${mode}-${role?.uuid ?? 'new'}`}
      token={token}
      mode={mode}
      role={role}
      onClose={onClose}
      onSaved={onSaved}
    />
  )
}

function AdminRoleModalForm({
  token,
  mode,
  role,
  onClose,
  onSaved,
}: Omit<Props, 'open'>) {
  const [name, setName] = useState(() => (mode === 'edit' && role ? role.name : ''))
  const [slug, setSlug] = useState(() => (mode === 'edit' && role ? role.slug : ''))
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const isEdit = mode === 'edit'

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    const trimmed = name.trim()
    if (isEdit && role) {
      const res = await apiFetch(`/api/admin/roles/${role.uuid}`, {
        method: 'PATCH',
        token,
        body: JSON.stringify({ name: trimmed }),
      })
      setSaving(false)
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setError((j as { detail?: string }).detail ?? 'No se pudo guardar el rol')
        return
      }
      onSaved()
      onClose()
      return
    }

    const body: Record<string, string> = { name: trimmed }
    if (slug.trim()) body.slug = slug.trim().toUpperCase().replace(/\s+/g, '_')
    const res = await apiFetch('/api/admin/roles', {
      method: 'POST',
      token,
      body: JSON.stringify(body),
    })
    setSaving(false)
    if (!res.ok) {
      const j = await res.json().catch(() => ({}))
      setError((j as { detail?: string }).detail ?? 'No se pudo crear el rol')
      return
    }
    onSaved()
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="presentation">
      <form
        className="w-full max-w-md rounded-lg border border-black/10 bg-white p-6 shadow-lg"
        onSubmit={(e) => void submit(e)}
      >
        <h2 className="text-lg font-semibold text-ink">{isEdit ? 'Editar rol' : 'Nuevo rol'}</h2>
        <div className="mt-4 space-y-3">
          <div>
            <label className="du-label" htmlFor="role-name">
              Nombre
            </label>
            <input
              id="role-name"
              className="du-input mt-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          {isEdit ? (
            <div>
              <label className="du-label" htmlFor="role-slug-readonly">
                Slug
              </label>
              <input id="role-slug-readonly" className="du-input mt-1 bg-black/[0.03]" value={slug} readOnly />
            </div>
          ) : (
            <div>
              <label className="du-label" htmlFor="role-slug">
                Slug <span className="font-normal text-muted">(opcional)</span>
              </label>
              <input
                id="role-slug"
                className="du-input mt-1"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="AUDITOR_INTERNO"
              />
            </div>
          )}
          {error ? <p className="text-sm text-primary">{error}</p> : null}
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink" onClick={onClose}>
            Cancelar
          </button>
          <PrimaryButton type="submit" disabled={saving}>
            {saving ? 'Guardando…' : isEdit ? 'Guardar cambios' : 'Crear rol'}
          </PrimaryButton>
        </div>
      </form>
    </div>
  )
}

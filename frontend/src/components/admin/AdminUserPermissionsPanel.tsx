import { useEffect, useMemo, useState } from 'react'

import { apiFetch } from '../../api/client'

type PermissionRow = { key: string; label: string; category: string }

type Props = {
  token: string
  userUuid: string
  open: boolean
  onClose: () => void
}

export function AdminUserPermissionsPanel({ token, userUuid, open, onClose }: Props) {
  const [catalog, setCatalog] = useState<PermissionRow[]>([])
  const [rolePermissions, setRolePermissions] = useState<string[]>([])
  const [overrides, setOverrides] = useState<Record<string, boolean | null>>({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    void (async () => {
      setLoading(true)
      setError(null)
      const [catRes, detailRes] = await Promise.all([
        apiFetch('/api/admin/permissions/catalog', { token }),
        apiFetch(`/api/admin/users/${userUuid}/permissions`, { token }),
      ])
      setLoading(false)
      if (!catRes.ok || !detailRes.ok) {
        setError('No se pudieron cargar los permisos')
        return
      }
      setCatalog((await catRes.json()) as PermissionRow[])
      const detail = (await detailRes.json()) as {
        permissions: string[]
        overrides: { permission_key: string; granted: boolean }[]
      }
      setRolePermissions(detail.permissions)
      const map: Record<string, boolean | null> = {}
      for (const o of detail.overrides) {
        map[o.permission_key] = o.granted
      }
      setOverrides(map)
    })()
  }, [open, token, userUuid])

  const effective = useMemo(() => {
    const base = new Set(rolePermissions)
    for (const [key, granted] of Object.entries(overrides)) {
      if (granted === null) continue
      if (granted) base.add(key)
      else base.delete(key)
    }
    return base
  }, [rolePermissions, overrides])

  async function save() {
    setSaving(true)
    setError(null)
    const payload = Object.entries(overrides)
      .filter(([, granted]) => granted !== null)
      .map(([permission_key, granted]) => ({ permission_key, granted: granted as boolean }))
    const res = await apiFetch(`/api/admin/users/${userUuid}/permissions`, {
      method: 'PUT',
      token,
      body: JSON.stringify({ overrides: payload }),
    })
    setSaving(false)
    if (!res.ok) {
      setError('No se pudieron guardar los overrides')
      return
    }
    onClose()
  }

  if (!open) return null

  return (
    <div className="mt-4 rounded-lg border border-black/10 p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">Permisos especiales</h3>
        <button type="button" className="text-sm text-muted hover:text-ink" onClick={onClose}>
          Cerrar
        </button>
      </div>
      {loading ? <p className="du-meta mt-2">Cargando…</p> : null}
      {error ? <p className="mt-2 text-sm text-primary">{error}</p> : null}
      {!loading ? (
        <ul className="mt-3 max-h-48 space-y-2 overflow-y-auto">
          {catalog.map((perm) => {
            const override = overrides[perm.key]
            const fromRole = rolePermissions.includes(perm.key)
            const effectiveGranted = effective.has(perm.key)
            return (
              <li key={perm.key} className="flex items-center justify-between gap-2 text-sm">
                <span className="text-ink">{perm.label}</span>
                <select
                  className="du-input py-1 text-xs"
                  value={override === null || override === undefined ? 'inherit' : override ? 'grant' : 'deny'}
                  onChange={(e) => {
                    const v = e.target.value
                    setOverrides((prev) => ({
                      ...prev,
                      [perm.key]: v === 'inherit' ? null : v === 'grant',
                    }))
                  }}
                >
                  <option value="inherit">{fromRole ? 'Del rol (sí)' : 'Del rol (no)'}</option>
                  <option value="grant">Forzar sí</option>
                  <option value="deny">Forzar no</option>
                </select>
                <span className={`text-xs ${effectiveGranted ? 'text-green-700' : 'text-muted'}`}>
                  {effectiveGranted ? 'Efectivo: sí' : 'Efectivo: no'}
                </span>
              </li>
            )
          })}
        </ul>
      ) : null}
      <div className="mt-3 flex justify-end">
        <button
          type="button"
          className="rounded-md bg-primary px-3 py-1.5 text-sm text-white disabled:opacity-50"
          disabled={saving}
          onClick={() => void save()}
        >
          {saving ? 'Guardando…' : 'Guardar overrides'}
        </button>
      </div>
    </div>
  )
}

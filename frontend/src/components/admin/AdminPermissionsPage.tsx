import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { apiFetch } from '../../api/client'
import { permissionCategoryStyle } from '../../constants/permissionCategories'
import { confirmDestructive } from '../../lib/duplaAlert'
import { Card } from '../Card'
import { PrimaryButton } from '../PrimaryButton'
import { AdminRoleModal } from './AdminRoleModal'

type PermissionRow = { key: string; label: string; category: string }
type RoleRow = {
  uuid: string
  slug: string
  name: string
  is_system: boolean
  is_deletable: boolean
  permissions: string[]
}

type Props = {
  token: string
  onRolesChanged?: () => void
}

export function AdminPermissionsPage({ token, onRolesChanged }: Props) {
  const onRolesChangedRef = useRef(onRolesChanged)
  useEffect(() => {
    onRolesChangedRef.current = onRolesChanged
  }, [onRolesChanged])

  const [catalog, setCatalog] = useState<PermissionRow[]>([])
  const [roles, setRoles] = useState<RoleRow[]>([])
  const [selectedRoleUuid, setSelectedRoleUuid] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [roleModalOpen, setRoleModalOpen] = useState(false)
  const [roleModalMode, setRoleModalMode] = useState<'create' | 'edit'>('create')
  const [editingRole, setEditingRole] = useState<RoleRow | null>(null)
  const [deletingRoleUuid, setDeletingRoleUuid] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setError(null)
    const [catRes, rolesRes] = await Promise.all([
      apiFetch('/api/admin/permissions/catalog', { token }),
      apiFetch('/api/admin/roles', { token }),
    ])
    if (!catRes.ok || !rolesRes.ok) {
      setError('No se pudo cargar la matriz de permisos')
      return
    }
    setCatalog((await catRes.json()) as PermissionRow[])
    const nextRoles = (await rolesRes.json()) as RoleRow[]
    setRoles(nextRoles)
    setSelectedRoleUuid((prev) => {
      if (prev && nextRoles.some((r) => r.uuid === prev)) return prev
      return nextRoles[0]?.uuid ?? null
    })
  }, [token])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setLoading(true)
      await refresh()
      if (!cancelled) setLoading(false)
    })()
    return () => {
      cancelled = true
    }
  }, [refresh])

  const selectedRole = useMemo(
    () => roles.find((r) => r.uuid === selectedRoleUuid) ?? null,
    [roles, selectedRoleUuid],
  )

  const grouped = useMemo(() => {
    const map = new Map<string, PermissionRow[]>()
    for (const row of catalog) {
      const list = map.get(row.category) ?? []
      list.push(row)
      map.set(row.category, list)
    }
    return [...map.entries()]
  }, [catalog])

  const grantedCount = selectedRole?.permissions.length ?? 0

  async function togglePermission(permissionKey: string, granted: boolean) {
    if (!selectedRole) return
    const next = granted
      ? [...selectedRole.permissions, permissionKey]
      : selectedRole.permissions.filter((k) => k !== permissionKey)
    setSavingKey(permissionKey)
    const res = await apiFetch(`/api/admin/roles/${selectedRole.uuid}/permissions`, {
      method: 'PUT',
      token,
      body: JSON.stringify({ permissions: next }),
    })
    setSavingKey(null)
    if (!res.ok) {
      setError('No se pudo guardar el permiso')
      return
    }
    await refresh()
  }

  function openCreateRole() {
    setRoleModalMode('create')
    setEditingRole(null)
    setRoleModalOpen(true)
  }

  function openEditRole(role: RoleRow) {
    setRoleModalMode('edit')
    setEditingRole(role)
    setRoleModalOpen(true)
  }

  async function deleteRole(role: RoleRow) {
    if (
      !(await confirmDestructive({
        title: `¿Eliminar rol «${role.name}»?`,
        text: 'Los usuarios con este rol perderán esos permisos. Esta acción no se puede deshacer.',
      }))
    ) {
      return
    }
    setDeletingRoleUuid(role.uuid)
    setError(null)
    const res = await apiFetch(`/api/admin/roles/${role.uuid}`, { method: 'DELETE', token })
    setDeletingRoleUuid(null)
    if (!res.ok) {
      const j = await res.json().catch(() => ({}))
      setError((j as { detail?: string }).detail ?? 'No se pudo eliminar el rol')
      return
    }
    if (selectedRoleUuid === role.uuid) {
      setSelectedRoleUuid(null)
    }
    await refresh()
    onRolesChangedRef.current?.()
  }

  if (loading) {
    return <p className="du-meta">Cargando matriz…</p>
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="du-section-title">Roles y permisos</h2>
          <p className="du-meta mt-1">
            Elige un rol y activa los permisos que debe tener. Los overrides por usuario se editan en cada perfil.
          </p>
        </div>
        <PrimaryButton type="button" onClick={openCreateRole}>
          Nuevo rol
        </PrimaryButton>
      </div>

      {error ? <p className="text-sm text-primary">{error}</p> : null}

      <div className="du-filter-bar">
        <span className="text-sm font-medium text-muted">Rol</span>
        <div className="flex min-w-0 flex-1 flex-wrap gap-2">
          {roles.map((role) => {
            const active = role.uuid === selectedRoleUuid
            return (
              <button
                key={role.uuid}
                type="button"
                onClick={() => setSelectedRoleUuid(role.uuid)}
                className={`rounded-full border px-3.5 py-1.5 text-sm font-semibold transition ${
                  active
                    ? 'border-primary bg-primary text-white shadow-[0_4px_14px_rgba(193,13,18,0.28)]'
                    : 'border-black/12 bg-white text-ink hover:border-primary/30 hover:bg-primary/5'
                }`}
              >
                {role.name}
              </button>
            )
          })}
        </div>
      </div>

      {selectedRole ? (
        <Card className="border-primary/15 bg-primary/[0.03] p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-lg font-semibold text-ink">{selectedRole.name}</p>
              <p className="du-meta mt-0.5 font-mono text-xs">{selectedRole.slug}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex rounded-full bg-primary/12 px-2.5 py-0.5 text-xs font-bold text-primary">
                {grantedCount} de {catalog.length} permisos
              </span>
              {selectedRole.is_system ? (
                <span className="inline-flex rounded-full bg-white px-2.5 py-0.5 text-xs font-medium text-muted ring-1 ring-black/10">
                  Rol del sistema
                </span>
              ) : null}
              <button
                type="button"
                className="du-pill-action py-1 text-xs"
                onClick={() => openEditRole(selectedRole)}
              >
                Editar nombre
              </button>
              {selectedRole.is_deletable ? (
                <button
                  type="button"
                  className="rounded-md border border-primary/30 px-3 py-1 text-xs font-semibold text-primary hover:bg-primary/5 disabled:opacity-50"
                  disabled={deletingRoleUuid === selectedRole.uuid}
                  onClick={() => void deleteRole(selectedRole)}
                >
                  {deletingRoleUuid === selectedRole.uuid ? 'Eliminando…' : 'Eliminar rol'}
                </button>
              ) : null}
            </div>
          </div>
        </Card>
      ) : null}

      {!selectedRole ? (
        <Card className="p-6">
          <p className="du-meta">No hay roles disponibles. Crea uno para empezar.</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {grouped.map(([category, rows]) => {
            const style = permissionCategoryStyle(category)
            const sectionGranted = rows.filter((p) => selectedRole.permissions.includes(p.key)).length
            return (
              <Card key={category} className={`overflow-hidden border-l-4 p-0 ${style.border}`}>
                <div className={`flex flex-wrap items-center justify-between gap-2 px-4 py-3 sm:px-5 ${style.bg}`}>
                  <div className="flex items-center gap-2">
                    <span className={`size-2 shrink-0 rounded-full ${style.dot}`} aria-hidden />
                    <h3 className="text-sm font-bold uppercase tracking-wide text-ink">{category}</h3>
                  </div>
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${style.badge}`}>
                    {sectionGranted}/{rows.length}
                  </span>
                </div>
                <ul className="divide-y divide-black/6">
                  {rows.map((perm) => {
                    const checked = selectedRole.permissions.includes(perm.key)
                    const busy = savingKey === perm.key
                    return (
                      <li key={perm.key}>
                        <label
                          className={`flex cursor-pointer items-center justify-between gap-4 px-4 py-3.5 sm:px-5 ${
                            checked ? 'bg-white' : 'bg-white/60'
                          } ${busy ? 'opacity-60' : 'hover:bg-black/[0.02]'}`}
                        >
                          <div className="min-w-0">
                            <p className="font-medium text-ink">{perm.label}</p>
                            <p className="du-meta mt-0.5 font-mono text-xs">{perm.key}</p>
                          </div>
                          <span className="relative inline-flex shrink-0 items-center">
                            <input
                              type="checkbox"
                              className="peer sr-only"
                              checked={checked}
                              disabled={busy}
                              onChange={(e) => void togglePermission(perm.key, e.target.checked)}
                            />
                            <span
                              className={`h-7 w-12 rounded-full transition ${
                                checked ? 'bg-primary' : 'bg-black/15'
                              } peer-focus-visible:ring-2 peer-focus-visible:ring-primary/35 peer-focus-visible:ring-offset-2`}
                              aria-hidden
                            />
                            <span
                              className={`pointer-events-none absolute left-0.5 top-0.5 size-6 rounded-full bg-white shadow transition ${
                                checked ? 'translate-x-5' : 'translate-x-0'
                              }`}
                              aria-hidden
                            />
                          </span>
                        </label>
                      </li>
                    )
                  })}
                </ul>
              </Card>
            )
          })}
        </div>
      )}

      <AdminRoleModal
        token={token}
        open={roleModalOpen}
        mode={roleModalMode}
        role={editingRole}
        onClose={() => setRoleModalOpen(false)}
        onSaved={() => {
          void refresh().then(() => onRolesChangedRef.current?.())
        }}
      />
    </div>
  )
}

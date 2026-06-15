import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { X } from 'lucide-react'

import { ROLE_LABELS, USER_ROLES, type UserRole } from '../../constants/userRoles'
import type { DirectoryUserRow } from '../../lib/directoryUsers'
import { formatPersonFullName } from '../../lib/personDisplay'

/** Igual que `settings.architecture_module_id` en el backend. */
const ARCHITECTURE_MODULE_ID = 1

function hasArchitectureAccess(u: DirectoryUserRow): boolean {
  return u.module_ids.includes(ARCHITECTURE_MODULE_ID)
}

/** Texto buscable: nombres, correo completo y parte local (p. ej. «tester» en tester@dupla.demo). */
function searchableBlob(u: DirectoryUserRow): string {
  const local = u.email.includes('@') ? (u.email.split('@')[0] ?? '') : ''
  return `${u.first_name} ${u.last_name} ${u.email} ${local}`
}

function foldDiacritics(s: string): string {
  return s.normalize('NFD').replace(/\p{M}/gu, '')
}

function userMatchesQuery(u: DirectoryUserRow, raw: string): boolean {
  const q = foldDiacritics(raw.trim().toLowerCase())
  if (!q) return true
  const hay = foldDiacritics(searchableBlob(u).toLowerCase())
  const parts = q.split(/\s+/).filter(Boolean)
  return parts.every((p) => hay.includes(p))
}

type Props = {
  users: DirectoryUserRow[]
  /** Incluidos siempre (p. ej. creador); no se quitan ni se buscan otra vez */
  lockedUuids: Set<string>
  /** Uuids adicionales con acceso */
  extraSelected: Set<string>
  onExtraChange: (next: Set<string>) => void
  disabled?: boolean
  /** Texto de ayuda debajo del campo de búsqueda */
  hint?: string
}

export function ProjectMemberPicker({
  users,
  lockedUuids,
  extraSelected,
  onExtraChange,
  disabled = false,
  hint,
}: Props) {
  const baseId = useId()
  const searchId = `${baseId}-search`
  const listId = `${baseId}-list`
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [listOpen, setListOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedQuery(query), 300)
    return () => window.clearTimeout(id)
  }, [query])

  const lockedUsers = useMemo(() => users.filter((u) => lockedUuids.has(u.uuid)), [users, lockedUuids])
  const lockedMissingCount = Math.max(0, lockedUuids.size - lockedUsers.length)

  /** Solo quienes pueden ser miembros del proyecto (módulo Arquitectura). */
  const pickable = useMemo(() => {
    return users.filter(
      (u) =>
        hasArchitectureAccess(u) &&
        !lockedUuids.has(u.uuid) &&
        !extraSelected.has(u.uuid),
    )
  }, [users, lockedUuids, extraSelected])

  const eligibleCountByRole = useMemo(() => {
    const map = new Map<UserRole, number>()
    for (const role of USER_ROLES) {
      const n = users.filter(
        (u) =>
          u.role === role &&
          hasArchitectureAccess(u) &&
          !lockedUuids.has(u.uuid) &&
          !extraSelected.has(u.uuid),
      ).length
      map.set(role, n)
    }
    return map
  }, [users, lockedUuids, extraSelected])

  const filteredPickable = useMemo(() => {
    if (!debouncedQuery.trim()) return pickable
    return pickable.filter((u) => userMatchesQuery(u, debouncedQuery))
  }, [pickable, debouncedQuery])

  const selectedExtras = useMemo(() => {
    return users.filter((u) => extraSelected.has(u.uuid))
  }, [users, extraSelected])

  useEffect(() => {
    function onDocMouseDown(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setListOpen(false)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    return () => document.removeEventListener('mousedown', onDocMouseDown)
  }, [])

  function addUuid(uuid: string) {
    onExtraChange(new Set([...extraSelected, uuid]))
    setQuery('')
    setListOpen(false)
  }

  function addEntireRole(role: UserRole) {
    const ids = users
      .filter(
        (u) =>
          u.role === role &&
          hasArchitectureAccess(u) &&
          !lockedUuids.has(u.uuid) &&
          !extraSelected.has(u.uuid),
      )
      .map((u) => u.uuid)
    if (ids.length === 0) return
    onExtraChange(new Set([...extraSelected, ...ids]))
  }

  function removeUuid(uuid: string) {
    const next = new Set(extraSelected)
    next.delete(uuid)
    onExtraChange(next)
  }

  return (
    <div className="space-y-4">
      {lockedUsers.length > 0 ? (
        <div>
          <p className="text-xs font-medium text-muted">Siempre con acceso</p>
          <ul className="mt-1.5 space-y-1 text-sm">
            {lockedUsers.map((u) => (
              <li key={u.uuid} className="text-ink">
                <span className="font-medium">{formatPersonFullName(u.first_name, u.last_name, u.email)}</span>
                <span className="du-meta"> · {u.email}</span>
                <span className="du-meta"> (creador)</span>
              </li>
            ))}
          </ul>
        </div>
      ) : lockedUuids.size > 0 ? (
        <p className="text-sm text-ink">
          El creador del proyecto sigue teniendo acceso.
          {lockedMissingCount > 0 ? (
            <span className="du-meta">
              {' '}
              (No aparece en el listado cargado; revisa la administración de usuarios.)
            </span>
          ) : null}
        </p>
      ) : null}

      <div>
        <p className="du-label">Por rol</p>
        <p className="mt-0.5 text-xs text-muted">
          Añade de una vez a todas las personas con ese rol que tengan acceso al módulo Arquitectura (como en
          Usuarios).
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {USER_ROLES.map((role) => {
            const n = eligibleCountByRole.get(role) ?? 0
            const label = ROLE_LABELS[role]
            return (
              <button
                key={role}
                type="button"
                disabled={disabled || n === 0}
                className="inline-flex items-center gap-1.5 rounded-lg border border-black/12 bg-white px-3 py-2 text-sm font-medium text-ink shadow-sm transition hover:bg-black/4 disabled:cursor-not-allowed disabled:opacity-45"
                onClick={() => addEntireRole(role)}
              >
                + {label}
                {n > 0 ? (
                  <span className="rounded-full bg-primary/15 px-1.5 py-0.5 text-xs font-semibold text-primary">
                    {n}
                  </span>
                ) : null}
              </button>
            )
          })}
        </div>
      </div>

      <div ref={wrapRef} className="relative">
        <label htmlFor={searchId} className="du-label">
          Por persona
        </label>
        <input
          id={searchId}
          type="search"
          autoComplete="off"
          placeholder="Buscar por nombre o correo…"
          className="du-input mt-1 w-full"
          value={query}
          disabled={disabled}
          aria-autocomplete="list"
          aria-controls={listOpen ? listId : undefined}
          aria-expanded={listOpen}
          onChange={(e) => {
            setQuery(e.target.value)
            setListOpen(true)
          }}
          onFocus={() => setListOpen(true)}
        />
        {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}

        {listOpen && !disabled && filteredPickable.length > 0 ? (
          <ul
            id={listId}
            role="listbox"
            className="absolute left-0 right-0 z-20 mt-1 max-h-48 overflow-y-auto rounded-lg border border-black/10 bg-white py-1 shadow-lg"
          >
            {filteredPickable.map((u) => (
              <li key={u.uuid} role="presentation">
                <button
                  type="button"
                  role="option"
                  className="flex w-full flex-col items-start px-3 py-2 text-left text-sm hover:bg-black/4"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => addUuid(u.uuid)}
                >
                  <span className="font-medium text-ink">
                    {formatPersonFullName(u.first_name, u.last_name, u.email)}
                  </span>
                  <span className="text-xs text-muted">
                    {u.email}
                    {u.role ? (
                      <span className="text-muted"> · {ROLE_LABELS[u.role as UserRole] ?? u.role}</span>
                    ) : null}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        {listOpen &&
        !disabled &&
        debouncedQuery.trim().length > 0 &&
        filteredPickable.length === 0 &&
        pickable.length > 0 ? (
          <p className="mt-2 text-xs text-muted" role="status">
            No hay coincidencias. Prueba con otra parte del nombre o del correo.
          </p>
        ) : null}
      </div>

      {selectedExtras.length > 0 ? (
        <div>
          <p className="text-xs font-medium text-muted">Añadidas al proyecto</p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {selectedExtras.map((u) => (
              <li key={u.uuid}>
                <span className="inline-flex max-w-full items-center gap-1 rounded-full border border-black/12 bg-primary/6 py-1 pl-2.5 pr-1 text-sm text-ink">
                  <span className="min-w-0 truncate">
                    {formatPersonFullName(u.first_name, u.last_name, u.email)}
                    {u.role ? (
                      <span className="du-meta"> · {ROLE_LABELS[u.role as UserRole] ?? u.role}</span>
                    ) : null}
                  </span>
                  <button
                    type="button"
                    className="shrink-0 rounded-full p-1 text-muted hover:bg-black/10 hover:text-ink"
                    disabled={disabled}
                    aria-label={`Quitar a ${formatPersonFullName(u.first_name, u.last_name, u.email)}`}
                    onClick={() => removeUuid(u.uuid)}
                  >
                    <X className="h-3.5 w-3.5" aria-hidden />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-xs text-muted">
          Nadie más añadido aún. Usa los botones de rol, o el buscador para una persona concreta.
        </p>
      )}
    </div>
  )
}

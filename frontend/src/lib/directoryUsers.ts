/**
 * Usuarios listados desde `/api/admin/users` u otras rutas de directorio.
 * Normalizamos claves por si la API o capas intermedias usan otra convención.
 */
export type DirectoryUserRow = {
  uuid: string
  email: string
  first_name: string
  last_name: string
  /** Rol del usuario (vacío si el listado no lo trae). */
  role: string
  /** Módulos asignados (p. ej. 1 = Arquitectura). */
  module_ids: number[]
}

const UUID_STRING_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** Rechaza valores como "null", "undefined" o texto que no sea UUID. */
export function isValidUuidString(value: string): boolean {
  return UUID_STRING_RE.test(value.trim())
}

export function normalizeDirectoryUser(raw: unknown): DirectoryUserRow | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  const rawId = o.uuid != null ? o.uuid : o.id
  const uuid = rawId != null ? String(rawId).trim() : ''
  if (!isValidUuidString(uuid)) return null
  const fn =
    typeof o.first_name === 'string'
      ? o.first_name
      : typeof o.firstName === 'string'
        ? o.firstName
        : ''
  const ln =
    typeof o.last_name === 'string'
      ? o.last_name
      : typeof o.lastName === 'string'
        ? o.lastName
        : ''
  const role = typeof o.role === 'string' ? o.role : ''
  let moduleIds: number[] = []
  if (Array.isArray(o.module_ids)) {
    moduleIds = o.module_ids.filter((x): x is number => typeof x === 'number')
  } else if (Array.isArray((o as Record<string, unknown>).moduleIds)) {
    moduleIds = ((o as Record<string, unknown>).moduleIds as unknown[]).filter(
      (x): x is number => typeof x === 'number',
    )
  }

  return {
    uuid,
    email: typeof o.email === 'string' ? o.email : String(o.email ?? ''),
    first_name: fn,
    last_name: ln,
    role,
    module_ids: moduleIds,
  }
}

export function normalizeDirectoryUsers(raw: unknown): DirectoryUserRow[] {
  if (!Array.isArray(raw)) return []
  return raw.map(normalizeDirectoryUser).filter((x): x is DirectoryUserRow => x !== null)
}

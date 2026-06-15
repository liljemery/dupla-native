import { apiFetch } from '../api/client'

import type { DirectoryUserRow } from './directoryUsers'
import { normalizeDirectoryUsers } from './directoryUsers'

const STORAGE_KEY = 'dupla-admin-users-directory-v4'
/** Un día en milisegundos. */
const TTL_MS = 24 * 60 * 60 * 1000

type StoredPayload = {
  fetchedAt: number
  users: DirectoryUserRow[]
}

function safeRead(): StoredPayload | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const p = JSON.parse(raw) as StoredPayload
    if (typeof p.fetchedAt !== 'number' || !Array.isArray(p.users)) {
      return null
    }
    if (Date.now() - p.fetchedAt > TTL_MS) {
      localStorage.removeItem(STORAGE_KEY)
      return null
    }
    return p
  } catch {
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      /* ignore */
    }
    return null
  }
}

/** Lista en caché si sigue vigente (menos de 24 h); si no, `null`. */
export function getCachedAdminDirectoryUsersIfFresh(): DirectoryUserRow[] | null {
  const p = safeRead()
  return p ? normalizeDirectoryUsers(p.users) : null
}

function safeWrite(users: DirectoryUserRow[]): void {
  try {
    const payload: StoredPayload = {
      fetchedAt: Date.now(),
      users: normalizeDirectoryUsers(users),
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  } catch {
    /* quota u modo privado */
  }
}

/** Tras crear o editar usuarios, llamar para forzar un fetch fresco en la próxima carga. */
export function invalidateAdminUsersDirectoryCache(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

/**
 * Carga el directorio de usuarios admin: primero caché (24 h), si no hay, GET `/api/admin/users`.
 * `forceRefresh` omite caché (útil al asignar miembros: evita UUIDs de usuarios ya borrados).
 * Devuelve `null` si la petición falla (la UI puede mantener el estado anterior).
 */
export async function loadAdminDirectoryUsers(
  token: string,
  options?: { forceRefresh?: boolean },
): Promise<DirectoryUserRow[] | null> {
  if (!options?.forceRefresh) {
    const cached = getCachedAdminDirectoryUsersIfFresh()
    if (cached !== null) return cached
  }

  const res = await apiFetch('/api/admin/users', { token })
  if (!res.ok) return null

  const users = normalizeDirectoryUsers(await res.json())
  safeWrite(users)
  return users
}

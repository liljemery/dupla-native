import { AUTH_PERSIST_KEY } from '../store/authConstants'

type PersistedAuthState = {
  state?: {
    activeWorkspaceUuid?: string | null
  }
}

export function getActiveWorkspaceUuidFromStorage(): string | null {
  try {
    const raw = localStorage.getItem(AUTH_PERSIST_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as PersistedAuthState
    const v = parsed.state?.activeWorkspaceUuid
    return typeof v === 'string' && v.trim() ? v.trim() : null
  } catch {
    return null
  }
}

import { AUTH_PERSIST_KEY } from '../store/authConstants'
import { emitToast } from '../lib/toastEmitter'
import { getActiveWorkspaceUuidFromStorage } from '../lib/workspaceSession'

const base = import.meta.env.VITE_API_BASE ?? ''

export function apiUrl(path: string): string {
  if (path.startsWith('http')) return path
  const p = path.startsWith('/') ? path : `/${path}`
  return `${base}${p}`
}

function isAuthTokenRequest(path: string): boolean {
  try {
    const pathname = path.includes('://') ? new URL(path).pathname : path
    return (
      pathname.includes('/api/auth/token')
      || pathname.includes('/api/auth/forgot-password')
      || pathname.includes('/api/auth/reset-password')
    )
  } catch {
    return (
      path.includes('/api/auth/token')
      || path.includes('/api/auth/forgot-password')
      || path.includes('/api/auth/reset-password')
    )
  }
}

function handleUnauthorizedSession(path: string): void {
  if (isAuthTokenRequest(path)) return
  try {
    localStorage.removeItem(AUTH_PERSIST_KEY)
  } catch {
    /* ignore */
  }
  if (typeof window === 'undefined') return
  if (window.location.pathname.startsWith('/login')) return
  if (window.location.pathname.startsWith('/change-password')) return
  window.location.assign('/login')
}

// Status codes that should NOT emit a generic toast (callers handle them explicitly)
const SILENT_STATUSES = new Set([400, 401, 404, 502, 503, 504])

function isChatApiPath(path: string): boolean {
  try {
    const pathname = path.includes('://') ? new URL(path).pathname : path
    return pathname.startsWith('/api/chat')
  } catch {
    return path.includes('/api/chat')
  }
}

function shouldEmitErrorToast(path: string, status: number, silent?: boolean): boolean {
  if (silent) return false
  if (status < 400) return false
  if (SILENT_STATUSES.has(status)) return false
  if (isChatApiPath(path)) return false
  return true
}

export async function apiFetch(
  path: string,
  init: RequestInit & { token?: string | null; silent?: boolean } = {},
): Promise<Response> {
  const { token, silent, headers, ...rest } = init
  const h = new Headers(headers)
  if (token) {
    h.set('Authorization', `Bearer ${token}`)
  }
  const wsUuid = getActiveWorkspaceUuidFromStorage()
  if (wsUuid && !path.includes('/api/auth/')) {
    h.set('X-Workspace-Uuid', wsUuid)
  }
  if (!h.has('Content-Type') && rest.body && !(rest.body instanceof FormData)) {
    h.set('Content-Type', 'application/json')
  }
  const res = await fetch(apiUrl(path), { ...rest, headers: h })

  if (res.status === 401) {
    handleUnauthorizedSession(path)
  }

  if (shouldEmitErrorToast(path, res.status, silent)) {
    // Clone so the caller can still read the body
    res.clone().json().then((body: unknown) => {
      const detail =
        body && typeof body === 'object' && 'detail' in body
          ? String((body as { detail: unknown }).detail)
          : `Error ${res.status}`
      emitToast(detail, res.status >= 500 ? 'error' : 'warning')
    }).catch(() => {
      emitToast(`Error ${res.status}`, 'error')
    })
  }

  return res
}


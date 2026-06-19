import { Building2 } from 'lucide-react'

import { apiFetch } from '../api/client'
import { useAuthStore, type MeProfile } from '../store/authStore'

type Props = {
  className?: string
  variant?: 'badge' | 'toolbar'
}

export function WorkspaceContextBadge({ className, variant = 'badge' }: Props) {
  const name = useAuthStore((s) => s.activeWorkspaceName)
  if (!name) return null
  const base =
    variant === 'toolbar'
      ? 'inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-muted'
      : 'inline-flex items-center rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-muted shadow-sm'
  return (
    <span className={`${base} ${className ?? ''}`}>
      <Building2 className="size-3.5 shrink-0 text-primary" strokeWidth={2} aria-hidden />
      <span className="text-muted">Workspace</span>
      <span className="text-ink">{name}</span>
    </span>
  )
}

export function WorkspaceContextSelect({ className, variant = 'badge' }: Props) {
  const token = useAuthStore((s) => s.token)
  const activeUuid = useAuthStore((s) => s.activeWorkspaceUuid)
  const available = useAuthStore((s) => s.availableWorkspaces)
  const applyProfile = useAuthStore((s) => s.applyProfile)

  if (!token || available.length <= 1) {
    return <WorkspaceContextBadge className={className} variant={variant} />
  }

  const selectClass =
    variant === 'toolbar'
      ? 'rounded-full border border-slate-200 bg-slate-50 py-1.5 pl-3 pr-8 text-xs font-semibold text-ink outline-none focus-visible:ring-2 focus-visible:ring-primary/25'
      : 'rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs font-semibold text-ink'

  return (
    <label
      className={`inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-xs ${className ?? ''}`}
    >
      <Building2 className="size-3.5 shrink-0 text-primary" strokeWidth={2} aria-hidden />
      <span className="font-semibold text-muted">Workspace</span>
      <select
        className={selectClass}
        value={activeUuid ?? ''}
        onChange={(e) => {
          const uuid = e.target.value
          if (!uuid || uuid === activeUuid) return
          void (async () => {
            const res = await apiFetch('/api/me/preferences', {
              method: 'PATCH',
              token,
              body: JSON.stringify({ active_workspace_uuid: uuid }),
            })
            if (!res.ok) return
            const profile = (await res.json()) as MeProfile
            applyProfile(profile)
            window.location.reload()
          })()
        }}
      >
        {available.map((w) => (
          <option key={w.uuid} value={w.uuid}>{w.name}</option>
        ))}
      </select>
    </label>
  )
}

import { apiFetch } from '../api/client'
import { useAuthStore, type MeProfile } from '../store/authStore'

type Props = {
  className?: string
}

export function WorkspaceContextBadge({ className }: Props) {
  const name = useAuthStore((s) => s.activeWorkspaceName)
  if (!name) return null
  return (
    <span
      className={`inline-flex items-center rounded-full border border-black/12 bg-white px-3 py-1 text-xs font-semibold text-muted ${className ?? ''}`}
    >
      Workspace: <span className="ml-1 text-ink">{name}</span>
    </span>
  )
}

export function WorkspaceContextSelect({ className }: Props) {
  const token = useAuthStore((s) => s.token)
  const activeUuid = useAuthStore((s) => s.activeWorkspaceUuid)
  const available = useAuthStore((s) => s.availableWorkspaces)
  const applyProfile = useAuthStore((s) => s.applyProfile)

  if (!token || available.length <= 1) {
    return <WorkspaceContextBadge className={className} />
  }

  return (
    <label className={`inline-flex items-center gap-2 text-xs ${className ?? ''}`}>
      <span className="font-semibold text-muted">Workspace</span>
      <select
        className="rounded-lg border border-black/12 bg-white px-2 py-1.5 text-xs font-semibold text-ink"
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

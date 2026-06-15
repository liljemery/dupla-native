import { useEffect, useState } from 'react'

import { apiFetch } from '../api/client'
import { Card } from '../components/Card'
import { PrimaryButton } from '../components/PrimaryButton'
import { invalidateAdminUsersDirectoryCache } from '../lib/adminUsersDirectoryCache'
import { useAuthStore, type MeProfile } from '../store/authStore'

export function SettingsPage() {
  const token = useAuthStore((s) => s.token)
  const email = useAuthStore((s) => s.email)
  const firstName = useAuthStore((s) => s.firstName)
  const lastName = useAuthStore((s) => s.lastName)
  const activeWorkspaceUuid = useAuthStore((s) => s.activeWorkspaceUuid)
  const availableWorkspaces = useAuthStore((s) => s.availableWorkspaces)
  const applyProfile = useAuthStore((s) => s.applyProfile)
  const refreshProfile = useAuthStore((s) => s.refreshProfile)

  const [fn, setFn] = useState(firstName ?? '')
  const [ln, setLn] = useState(lastName ?? '')
  const [workspaceUuid, setWorkspaceUuid] = useState(activeWorkspaceUuid ?? '')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setFn(firstName ?? '')
    setLn(lastName ?? '')
    setWorkspaceUuid(activeWorkspaceUuid ?? '')
  }, [firstName, lastName, activeWorkspaceUuid])

  async function savePreferences() {
    if (!token) return
    setBusy(true)
    setMsg(null)
    try {
      const res = await apiFetch('/api/me/preferences', {
        method: 'PATCH',
        token,
        body: JSON.stringify({
          first_name: fn.trim(),
          last_name: ln.trim(),
          active_workspace_uuid: workspaceUuid || null,
        }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) {
        setMsg((j as { detail?: string }).detail ?? 'No se pudieron guardar las preferencias')
        return
      }
      applyProfile(j as MeProfile)
      invalidateAdminUsersDirectoryCache()
      setMsg('Preferencias guardadas.')
      window.location.reload()
    } finally {
      setBusy(false)
    }
  }

  async function changePassword() {
    if (!token) return
    setBusy(true)
    setMsg(null)
    try {
      const res = await apiFetch('/api/auth/change-password', {
        method: 'POST',
        token,
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) {
        setMsg((j as { detail?: string }).detail ?? 'No se pudo cambiar la contraseña')
        return
      }
      setCurrentPassword('')
      setNewPassword('')
      setMsg('Contraseña actualizada.')
      await refreshProfile()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 pb-8">
      <div>
        <h1 className="text-2xl font-bold text-ink">Configuración de usuario</h1>
        <p className="mt-1 text-sm text-muted">{email}</p>
      </div>

      {msg ? <p className="text-sm text-primary">{msg}</p> : null}

      <Card className="space-y-4 p-6">
        <h2 className="text-base font-semibold text-ink">Perfil</h2>
        <label className="block text-sm">
          <span className="font-medium text-ink">Nombre</span>
          <input
            className="mt-1 w-full rounded-lg border border-black/15 px-3 py-2"
            value={fn}
            onChange={(e) => setFn(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="font-medium text-ink">Apellido</span>
          <input
            className="mt-1 w-full rounded-lg border border-black/15 px-3 py-2"
            value={ln}
            onChange={(e) => setLn(e.target.value)}
          />
        </label>
      </Card>

      <Card className="space-y-4 p-6">
        <h2 className="text-base font-semibold text-ink">Workspace activo</h2>
        <p className="text-sm text-muted">
          Elige qué entorno de trabajo quieres ver. Los proyectos, chat y usuarios listados pertenecen solo a ese
          workspace.
        </p>
        <select
          className="w-full rounded-lg border border-black/15 px-3 py-2 text-sm"
          value={workspaceUuid}
          onChange={(e) => setWorkspaceUuid(e.target.value)}
        >
          {availableWorkspaces.map((w) => (
            <option key={w.uuid} value={w.uuid}>{w.name}</option>
          ))}
        </select>
        <PrimaryButton type="button" disabled={busy} onClick={() => void savePreferences()}>
          Guardar preferencias
        </PrimaryButton>
      </Card>

      <Card className="space-y-4 p-6">
        <h2 className="text-base font-semibold text-ink">Contraseña</h2>
        <label className="block text-sm">
          <span className="font-medium text-ink">Contraseña actual</span>
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-black/15 px-3 py-2"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="font-medium text-ink">Nueva contraseña</span>
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-black/15 px-3 py-2"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            minLength={8}
          />
        </label>
        <PrimaryButton type="button" disabled={busy || !currentPassword || newPassword.length < 8} onClick={() => void changePassword()}>
          Cambiar contraseña
        </PrimaryButton>
      </Card>
    </div>
  )
}

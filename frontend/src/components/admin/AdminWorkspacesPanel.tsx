import { useCallback, useEffect, useState } from 'react'

import { apiFetch } from '../../api/client'
import { Card } from '../Card'
import { PrimaryButton } from '../PrimaryButton'

type WorkspaceRow = {
  uuid: string
  name: string
  is_default?: boolean
}

type Props = {
  token: string
}

export function AdminWorkspacesPanel({ token }: Props) {
  const [rows, setRows] = useState<WorkspaceRow[]>([])
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [defaultName, setDefaultName] = useState('')
  const [newName, setNewName] = useState('')

  const refresh = useCallback(async () => {
    const res = await apiFetch('/api/admin/workspaces', { token })
    if (!res.ok) return
    setRows((await res.json()) as WorkspaceRow[])
  }, [token])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const unnamedDefault = rows.some((r) => r.is_default && r.name === 'Workspace 1')

  async function createWorkspace() {
    setBusy(true)
    setMsg(null)
    try {
      const body: Record<string, string> = { new_workspace_name: newName.trim() }
      if (unnamedDefault && defaultName.trim()) {
        body.default_workspace_name = defaultName.trim()
      }
      const res = await apiFetch('/api/admin/workspaces', {
        method: 'POST',
        token,
        body: JSON.stringify(body),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) {
        setMsg((j as { detail?: string }).detail ?? 'No se pudo crear el workspace')
        return
      }
      setCreateOpen(false)
      setDefaultName('')
      setNewName('')
      await refresh()
      setMsg('Workspace creado.')
      window.location.reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="space-y-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink">Workspaces</h2>
          <p className="mt-1 text-sm text-muted">
            Entornos aislados: proyectos, usuarios y chat no se comparten entre workspaces.
          </p>
        </div>
        <PrimaryButton type="button" onClick={() => setCreateOpen(true)}>
          Nuevo workspace
        </PrimaryButton>
      </div>
      {msg ? <p className="text-sm text-primary">{msg}</p> : null}
      <ul className="divide-y divide-black/8 rounded-lg border border-black/10">
        {rows.map((w) => (
          <li key={w.uuid} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
            <span className="font-medium text-ink">{w.name}</span>
            {w.is_default ? <span className="text-xs text-muted">Por defecto</span> : null}
          </li>
        ))}
      </ul>

      {createOpen ? (
        <div className="rounded-lg border border-black/10 bg-black/[0.02] p-4 space-y-3">
          {unnamedDefault ? (
            <label className="block text-sm">
              <span className="font-medium text-ink">Nombre del workspace actual</span>
              <input
                className="mt-1 w-full rounded-lg border border-black/15 px-3 py-2"
                value={defaultName}
                onChange={(e) => setDefaultName(e.target.value)}
                placeholder="Ej. Dupla principal"
              />
            </label>
          ) : null}
          <label className="block text-sm">
            <span className="font-medium text-ink">Nombre del nuevo workspace</span>
            <input
              className="mt-1 w-full rounded-lg border border-black/15 px-3 py-2"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Ej. Sucursal norte"
            />
          </label>
          <div className="flex gap-2">
            <PrimaryButton type="button" disabled={busy || !newName.trim()} onClick={() => void createWorkspace()}>
              Crear
            </PrimaryButton>
            <button
              type="button"
              className="rounded-lg border border-black/15 px-4 py-2 text-sm font-semibold"
              onClick={() => setCreateOpen(false)}
            >
              Cancelar
            </button>
          </div>
        </div>
      ) : null}
    </Card>
  )
}

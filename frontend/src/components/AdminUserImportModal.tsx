import { useEffect, useMemo, useState } from 'react'

import { apiFetch } from '../api/client'
import { invalidateAdminUsersDirectoryCache } from '../lib/adminUsersDirectoryCache'
import {
  downloadCredentialsCsv,
  downloadImportTemplate,
  parseUserImportText,
  validImportRows,
  type ImportCreatedUser,
  type ParsedImportRow,
} from '../lib/adminUserImport'
import { ROLE_LABELS, USER_ROLES, type UserRole } from '../constants/userRoles'
import { PrimaryButton } from './PrimaryButton'

type Props = {
  token: string
  open: boolean
  onClose: () => void
  onImported: () => void
}

type ImportResponse = {
  created: ImportCreatedUser[]
  skipped: Array<{ email: string; reason: string }>
  errors: Array<{ email: string; detail: string }>
}

type Step = 'input' | 'preview' | 'result'

export function AdminUserImportModal({ token, open, onClose, onImported }: Props) {
  const [step, setStep] = useState<Step>('input')
  const [rawText, setRawText] = useState('')
  const [parseErrors, setParseErrors] = useState<string[]>([])
  const [rows, setRows] = useState<ParsedImportRow[]>([])
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<ImportResponse | null>(null)

  useEffect(() => {
    if (!open) return
    setStep('input')
    setRawText('')
    setParseErrors([])
    setRows([])
    setSubmitError(null)
    setSubmitting(false)
    setResult(null)
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const validRows = useMemo(() => validImportRows(rows), [rows])

  function handleParse() {
    const parsed = parseUserImportText(rawText)
    setRows(parsed.rows)
    setParseErrors(parsed.errors)
    if (parsed.rows.length > 0) {
      setStep('preview')
    }
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    const text = await file.text()
    setRawText(text)
    event.target.value = ''
  }

  function updateRowRole(key: string, role: UserRole) {
    setRows((current) =>
      current.map((row) => (row.key === key ? { ...row, role, parseError: null } : row)),
    )
  }

  async function handleImport() {
    if (validRows.length === 0) return
    setSubmitting(true)
    setSubmitError(null)
    const res = await apiFetch('/api/admin/users/import', {
      method: 'POST',
      token,
      body: JSON.stringify({
        users: validRows.map((row) => ({
          email: row.email,
          first_name: row.first_name,
          last_name: row.last_name,
          role: row.role,
          module_ids: row.module_ids,
        })),
      }),
    })
    setSubmitting(false)
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      setSubmitError((body as { detail?: string }).detail ?? 'No se pudo importar usuarios')
      return
    }
    const body = (await res.json()) as ImportResponse
    setResult(body)
    setStep('result')
    if (body.created.length > 0) {
      invalidateAdminUsersDirectoryCache()
      onImported()
    }
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-lg border border-black/10 bg-white p-6 shadow-lg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-user-import-title"
      >
        <h2 id="admin-user-import-title" className="text-lg font-semibold text-ink">
          Importar usuarios
        </h2>
        <p className="mt-2 text-sm text-muted">
          Sube un CSV o pega datos desde Excel. Se generará una contraseña temporal por usuario.
        </p>

        {step === 'input' ? (
          <div className="mt-6 space-y-4">
            <div className="flex flex-wrap gap-2">
              <label className="inline-flex cursor-pointer items-center rounded-md border border-black/15 px-3 py-2 text-sm text-ink hover:bg-black/4">
                Seleccionar CSV
                <input type="file" accept=".csv,text/csv,text/plain" className="hidden" onChange={(e) => void handleFileChange(e)} />
              </label>
              <button
                type="button"
                className="rounded-md border border-black/15 px-3 py-2 text-sm text-ink hover:bg-black/4"
                onClick={downloadImportTemplate}
              >
                Descargar plantilla
              </button>
            </div>
            <div>
              <label className="du-label" htmlFor="import-paste">
                Pegar desde Excel o CSV
              </label>
              <textarea
                id="import-paste"
                className="du-input mt-1 min-h-48 font-mono text-xs"
                placeholder="NOMBRES Y APELLIDOS&#9;CARGO&#9;CORREO&#9;DEPARTAMENTO"
                value={rawText}
                onChange={(event) => setRawText(event.target.value)}
              />
            </div>
            {parseErrors.length > 0 ? (
              <ul className="list-disc space-y-1 pl-5 text-sm text-primary">
                {parseErrors.map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            ) : null}
            <div className="flex flex-wrap justify-end gap-2 pt-2">
              <button type="button" className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink" onClick={onClose}>
                Cancelar
              </button>
              <PrimaryButton type="button" disabled={rawText.trim().length === 0} onClick={handleParse}>
                Previsualizar
              </PrimaryButton>
            </div>
          </div>
        ) : null}

        {step === 'preview' ? (
          <div className="mt-6 space-y-4">
            <p className="text-sm text-muted">
              {validRows.length} usuario(s) listos · {rows.length - validRows.length} con error
            </p>
            <div className="overflow-x-auto rounded-md border border-black/10">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="bg-black/4 text-xs uppercase text-muted">
                  <tr>
                    <th className="px-3 py-2">Nombre</th>
                    <th className="px-3 py-2">Correo</th>
                    <th className="px-3 py-2">Departamento</th>
                    <th className="px-3 py-2">Rol</th>
                    <th className="px-3 py-2">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.key} className="border-t border-black/5">
                      <td className="px-3 py-2 text-ink">
                        {row.first_name} {row.last_name}
                      </td>
                      <td className="px-3 py-2 text-muted">{row.email}</td>
                      <td className="px-3 py-2 text-muted">{row.department || '—'}</td>
                      <td className="px-3 py-2">
                        <select
                          className="du-input py-1 text-xs"
                          value={row.role}
                          disabled={Boolean(row.parseError)}
                          onChange={(event) => updateRowRole(row.key, event.target.value as UserRole)}
                        >
                          {USER_ROLES.map((role) => (
                            <option key={role} value={role}>
                              {ROLE_LABELS[role]}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-2 text-xs text-primary">{row.parseError ?? 'OK'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {submitError ? <p className="text-sm text-primary">{submitError}</p> : null}
            <div className="flex flex-wrap justify-end gap-2 pt-2">
              <button type="button" className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink" onClick={() => setStep('input')}>
                Volver
              </button>
              <PrimaryButton type="button" disabled={submitting || validRows.length === 0} onClick={() => void handleImport()}>
                {submitting ? 'Importando…' : `Importar ${validRows.length} usuario(s)`}
              </PrimaryButton>
            </div>
          </div>
        ) : null}

        {step === 'result' && result ? (
          <div className="mt-6 space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-md border border-black/10 px-3 py-2 text-sm">
                <div className="text-xs uppercase text-muted">Creados</div>
                <div className="text-lg font-semibold text-ink">{result.created.length}</div>
              </div>
              <div className="rounded-md border border-black/10 px-3 py-2 text-sm">
                <div className="text-xs uppercase text-muted">Omitidos</div>
                <div className="text-lg font-semibold text-ink">{result.skipped.length}</div>
              </div>
              <div className="rounded-md border border-black/10 px-3 py-2 text-sm">
                <div className="text-xs uppercase text-muted">Errores</div>
                <div className="text-lg font-semibold text-ink">{result.errors.length}</div>
              </div>
            </div>

            {result.created.length > 0 ? (
              <div className="overflow-x-auto rounded-md border border-black/10">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="bg-black/4 text-xs uppercase text-muted">
                    <tr>
                      <th className="px-3 py-2">Correo</th>
                      <th className="px-3 py-2">Contraseña temporal</th>
                      <th className="px-3 py-2">Rol</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.created.map((user) => (
                      <tr key={user.uuid} className="border-t border-black/5">
                        <td className="px-3 py-2 text-muted">{user.email}</td>
                        <td className="px-3 py-2 font-mono text-xs text-ink">{user.password}</td>
                        <td className="px-3 py-2 text-muted">{ROLE_LABELS[user.role]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}

            {(result.skipped.length > 0 || result.errors.length > 0) && (
              <div className="space-y-2 text-sm text-muted">
                {result.skipped.map((item) => (
                  <p key={`skip-${item.email}`}>
                    Omitido {item.email}: {item.reason}
                  </p>
                ))}
                {result.errors.map((item) => (
                  <p key={`err-${item.email}`} className="text-primary">
                    Error {item.email}: {item.detail}
                  </p>
                ))}
              </div>
            )}

            <div className="flex flex-wrap justify-end gap-2 pt-2">
              {result.created.length > 0 ? (
                <button
                  type="button"
                  className="rounded-md border border-black/15 px-3 py-2 text-sm text-ink hover:bg-black/4"
                  onClick={() => downloadCredentialsCsv(result.created)}
                >
                  Descargar credenciales CSV
                </button>
              ) : null}
              <PrimaryButton type="button" onClick={onClose}>
                Cerrar
              </PrimaryButton>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

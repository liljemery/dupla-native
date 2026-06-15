import { useState } from 'react'
import { Eye, EyeOff, Lock } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { changePassword } from '../api/auth'
import { DuplaLogo } from '../components/DuplaLogo'
import { PrimaryButton } from '../components/PrimaryButton'
import { useAuthStore } from '../store/authStore'

export function ChangePasswordPage() {
  const navigate = useNavigate()
  const token = useAuthStore((s) => s.token)
  const logout = useAuthStore((s) => s.logout)
  const clearMustChangePassword = useAuthStore((s) => s.clearMustChangePassword)
  const email = useAuthStore((s) => s.email)

  const [currentPassword, setCurrentPassword] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (!token) {
      navigate('/login', { replace: true })
      return
    }
    if (password !== confirmPassword) {
      setError('Las contraseñas no coinciden.')
      return
    }
    if (password.length < 8) {
      setError('La contraseña debe tener al menos 8 caracteres.')
      return
    }
    if (password === currentPassword) {
      setError('La nueva contraseña debe ser distinta a la actual.')
      return
    }

    setLoading(true)
    try {
      await changePassword(token, currentPassword, password)
      clearMustChangePassword()
      navigate('/app/projects', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-dvh flex-col bg-white px-6 py-10 text-ink sm:px-10">
      <div className="mx-auto w-full max-w-md">
        <div className="mb-8 flex items-center gap-3">
          <div className="rounded-lg bg-primary/8 p-1.5 ring-1 ring-primary/15">
            <DuplaLogo className="h-8 w-auto max-w-[160px] object-contain object-left" />
          </div>
        </div>

        <header className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight text-ink">Cambia tu contraseña</h1>
          <p className="mt-2 text-base text-muted">
            {email
              ? `Por seguridad, ${email} debe usar una contraseña propia antes de entrar al panel.`
              : 'Por seguridad, debes elegir una contraseña propia antes de entrar al panel.'}
          </p>
        </header>

        <form onSubmit={onSubmit} className="space-y-5">
          <div>
            <label
              className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted"
              htmlFor="change-current-password"
            >
              Contraseña temporal
            </label>
            <div className="relative">
              <Lock
                className="pointer-events-none absolute left-3 top-1/2 size-4.5 -translate-y-1/2 text-muted"
                strokeWidth={1.75}
                aria-hidden
              />
              <input
                id="change-current-password"
                name="currentPassword"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="La que te entregaron"
                className="du-input mt-0 rounded-lg border-black/12 py-3 pl-10 pr-3.5"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                disabled={loading}
                required
              />
            </div>
          </div>

          <div>
            <label
              className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted"
              htmlFor="change-new-password"
            >
              Nueva contraseña
            </label>
            <div className="relative">
              <Lock
                className="pointer-events-none absolute left-3 top-1/2 size-4.5 -translate-y-1/2 text-muted"
                strokeWidth={1.75}
                aria-hidden
              />
              <input
                id="change-new-password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder="Mínimo 8 caracteres"
                className="du-input mt-0 rounded-lg border-black/12 py-3 pl-10 pr-11"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                required
                minLength={8}
              />
              <button
                type="button"
                className="absolute right-2 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-md text-muted outline-none transition-colors hover:bg-black/4 hover:text-ink focus-visible:ring-2 focus-visible:ring-primary/30"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
              >
                {showPassword ? (
                  <EyeOff className="size-4.5" strokeWidth={1.75} />
                ) : (
                  <Eye className="size-4.5" strokeWidth={1.75} />
                )}
              </button>
            </div>
          </div>

          <div>
            <label
              className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted"
              htmlFor="change-confirm-password"
            >
              Confirmar contraseña
            </label>
            <div className="relative">
              <Lock
                className="pointer-events-none absolute left-3 top-1/2 size-4.5 -translate-y-1/2 text-muted"
                strokeWidth={1.75}
                aria-hidden
              />
              <input
                id="change-confirm-password"
                name="confirmPassword"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder="Repite la contraseña"
                className="du-input mt-0 rounded-lg border-black/12 py-3 pl-10 pr-3.5"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={loading}
                required
                minLength={8}
              />
            </div>
          </div>

          {error ? (
            <p
              className="rounded-lg border border-primary/25 bg-primary/5 px-3 py-2.5 text-sm text-primary"
              role="alert"
            >
              {error}
            </p>
          ) : null}

          <PrimaryButton
            className="w-full rounded-lg py-3.5 text-base font-semibold normal-case tracking-normal"
            type="submit"
            disabled={loading}
          >
            {loading ? 'Guardando…' : 'Guardar y continuar'}
          </PrimaryButton>

          <button
            type="button"
            className="w-full rounded-lg px-3 py-2 text-sm text-muted hover:text-ink"
            onClick={() => {
              logout()
              navigate('/login', { replace: true })
            }}
          >
            Cerrar sesión
          </button>
        </form>
      </div>
    </div>
  )
}

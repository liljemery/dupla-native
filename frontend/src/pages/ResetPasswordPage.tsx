import { useMemo, useState } from 'react'
import { ArrowLeft, Eye, EyeOff, Lock } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { resetPassword } from '../api/auth'
import { DuplaLogo } from '../components/DuplaLogo'
import { PrimaryButton } from '../components/PrimaryButton'

export function ResetPasswordPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = useMemo(() => searchParams.get('token')?.trim() ?? '', [searchParams])

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (!token) {
      setError('Enlace inválido. Solicita uno nuevo desde la pantalla de inicio de sesión.')
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

    setLoading(true)
    try {
      await resetPassword(token, password)
      navigate('/login', { replace: true, state: { passwordReset: true } })
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

        <Link className="du-link mb-6 inline-flex items-center gap-1.5 text-sm font-medium" to="/login">
          <ArrowLeft className="size-4" strokeWidth={1.75} aria-hidden />
          Volver al inicio de sesión
        </Link>

        <header className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight text-ink">Nueva contraseña</h1>
          <p className="mt-2 text-base text-muted">Elige una contraseña segura para tu cuenta.</p>
        </header>

        {!token ? (
          <p className="rounded-lg border border-primary/25 bg-primary/5 px-3 py-2.5 text-sm text-primary" role="alert">
            Enlace inválido o incompleto.{' '}
            <Link className="du-link font-medium" to="/forgot-password">
              Solicitar un nuevo enlace
            </Link>
            .
          </p>
        ) : (
          <form onSubmit={onSubmit} className="space-y-5">
            <div>
              <label
                className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted"
                htmlFor="reset-password"
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
                  id="reset-password"
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
                htmlFor="reset-password-confirm"
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
                  id="reset-password-confirm"
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
              {loading ? 'Guardando…' : 'Guardar contraseña'}
            </PrimaryButton>
          </form>
        )}
      </div>
    </div>
  )
}

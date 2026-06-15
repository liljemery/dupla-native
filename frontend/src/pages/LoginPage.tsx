import { useState } from 'react'
import { Eye, EyeOff, Lock, Mail } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { DuplaLogo } from '../components/DuplaLogo'
import { PrimaryButton } from '../components/PrimaryButton'
import { useAuthStore } from '../store/authStore'

const SUPPORT_EMAIL =
  typeof import.meta.env.VITE_SUPPORT_EMAIL === 'string' ? import.meta.env.VITE_SUPPORT_EMAIL.trim() : ''

function supportMailto(subject: string): string {
  const q = new URLSearchParams()
  if (subject) q.set('subject', subject)
  const qs = q.toString()
  return `mailto:${SUPPORT_EMAIL}${qs ? `?${qs}` : ''}`
}

const LOGIN_SIDE_BG = `${import.meta.env.BASE_URL}window-login-image.jpg`

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((s) => s.login)
  const passwordResetSuccess = (location.state as { passwordReset?: boolean } | null)?.passwordReset === true
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const mustChangePassword = await login(email, password)
      navigate(mustChangePassword ? '/change-password' : '/app/projects', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error')
    } finally {
      setLoading(false)
    }
  }

  const footerSupportHref = SUPPORT_EMAIL ? supportMailto('Alta de cuenta — Dupla') : undefined

  return (
    <div className="flex min-h-dvh flex-col bg-white text-ink lg:flex-row">
      <aside className="relative flex min-h-[200px] shrink-0 flex-col justify-between overflow-hidden bg-primary px-6 py-8 text-white sm:px-10 lg:min-h-dvh lg:w-[42%] lg:max-w-xl lg:px-10 lg:py-12 xl:px-14">
        <div
          className="pointer-events-none absolute inset-0 bg-cover bg-center bg-no-repeat"
          style={{ backgroundImage: `url('${LOGIN_SIDE_BG}')` }}
          aria-hidden
        />
        <div
          className="pointer-events-none absolute inset-0 bg-primary/85"
          aria-hidden
        />
        <div
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(255,255,255,0.12),transparent_50%)]"
          aria-hidden
        />

        <div className="relative z-10 flex items-center gap-3">
          <div className="rounded-lg p-2 ring-1 ring-black/5">
            <DuplaLogo className="h-9 w-auto max-w-[200px] object-contain object-left sm:h-10" />
          </div>
        </div>

        <div className="relative z-10 flex flex-1 flex-col justify-center py-6 lg:py-12">
          <p className="max-w-md text-2xl font-light leading-snug tracking-tight text-white/95 sm:text-3xl lg:text-[1.65rem] lg:leading-tight xl:text-3xl">
            Gestión inteligente de proyectos de construcción
          </p>
          <span className="mt-5 block h-0.5 w-12 bg-white" aria-hidden />
        </div>

        <p className="relative z-10 text-xs leading-relaxed text-white/70">
          Versión {__APP_VERSION__}
          <span className="mx-2 text-white/40" aria-hidden>
            ·
          </span>
          © {new Date().getFullYear()} Grupo Dupla
        </p>
      </aside>

      <main className="flex flex-1 flex-col justify-center px-6 py-10 sm:px-10 lg:px-14 xl:px-20">
        <div className="mx-auto w-full max-w-md">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="rounded-lg bg-primary/8 p-1.5 ring-1 ring-primary/15">
              <DuplaLogo className="h-8 w-auto max-w-[160px] object-contain object-left" />
            </div>
          </div>

          <header className="mb-8">
            <h1 className="text-3xl font-bold tracking-tight text-ink sm:text-[2rem]">Bienvenido</h1>
            <p className="mt-2 text-base text-muted">
              Ingresa tus credenciales para continuar al panel de control.
            </p>
          </header>

          <form onSubmit={onSubmit} className="space-y-5">
            {passwordResetSuccess ? (
              <p
                className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800"
                role="status"
              >
                Contraseña actualizada. Inicia sesión con tu nueva contraseña.
              </p>
            ) : null}
            <div>
              <label
                className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted"
                htmlFor="login-email"
              >
                Correo electrónico
              </label>
              <div className="relative">
                <Mail
                  className="pointer-events-none absolute left-3 top-1/2 size-4.5 -translate-y-1/2 text-muted"
                  strokeWidth={1.75}
                  aria-hidden
                />
                <input
                  id="login-email"
                  name="email"
                  type="email"
                  inputMode="email"
                  autoComplete="username"
                  placeholder="nombre@empresa.com"
                  className="du-input mt-0 rounded-lg border-black/12 py-3 pl-10 pr-3.5"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                  required
                />
              </div>
            </div>

            <div>
              <label
                className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted"
                htmlFor="login-password"
              >
                Contraseña
              </label>
              <div className="relative">
                <Lock
                  className="pointer-events-none absolute left-3 top-1/2 size-4.5 -translate-y-1/2 text-muted"
                  strokeWidth={1.75}
                  aria-hidden
                />
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="••••••••"
                  className="du-input mt-0 rounded-lg border-black/12 py-3 pl-10 pr-11"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                  required
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

            <div className="text-right">
              <Link className="du-link text-sm font-medium" to="/forgot-password">
                ¿Olvidaste tu contraseña?
              </Link>
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
              {loading ? 'Ingresando…' : 'Ingresar'}
            </PrimaryButton>
          </form>

          <p className="mt-10 text-center text-sm text-muted">
            ¿No tienes una cuenta?{' '}
            {footerSupportHref ? (
              <a className="du-link font-semibold" href={footerSupportHref}>
                Contactar a soporte
              </a>
            ) : (
              <span className="font-semibold text-primary">Contactar a soporte</span>
            )}
          </p>
        </div>
      </main>
    </div>
  )
}

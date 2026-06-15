import { useState } from 'react'
import { ArrowLeft, Mail } from 'lucide-react'
import { Link } from 'react-router-dom'

import { requestPasswordReset } from '../api/auth'
import { DuplaLogo } from '../components/DuplaLogo'
import { PrimaryButton } from '../components/PrimaryButton'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [confirmation, setConfirmation] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const message = await requestPasswordReset(email)
      setConfirmation(message)
      setSent(true)
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
          <h1 className="text-3xl font-bold tracking-tight text-ink">Restablecer contraseña</h1>
          <p className="mt-2 text-base text-muted">
            {sent
              ? 'Revisa tu bandeja de entrada y sigue el enlace del correo.'
              : 'Te enviaremos un enlace para elegir una nueva contraseña.'}
          </p>
        </header>

        {sent ? (
          <div className="space-y-6">
            <p className="rounded-lg border border-black/10 bg-black/2 px-4 py-3 text-sm text-ink">
              {confirmation}
            </p>
            <PrimaryButton
              className="w-full rounded-lg py-3.5 text-base font-semibold normal-case tracking-normal"
              type="button"
              onClick={() => {
                setSent(false)
                setConfirmation(null)
              }}
            >
              Enviar otro correo
            </PrimaryButton>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-5">
            <div>
              <label
                className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted"
                htmlFor="forgot-email"
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
                  id="forgot-email"
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
              {loading ? 'Enviando…' : 'Enviar enlace'}
            </PrimaryButton>
          </form>
        )}
      </div>
    </div>
  )
}

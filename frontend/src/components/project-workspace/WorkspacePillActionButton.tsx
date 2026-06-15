import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Check, Loader2, X } from 'lucide-react'

import { useActionFeedback } from '../../hooks/useActionFeedback'

type ActionResult = boolean | void | Promise<boolean | void>

type Props = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onClick'> & {
  children: ReactNode
  onAction: () => ActionResult
  successLabel?: string
  runningLabel?: string
  errorLabel?: string
}

export function WorkspacePillActionButton({
  children,
  onAction,
  successLabel = 'Listo',
  runningLabel,
  errorLabel = 'Error',
  className = '',
  disabled,
  type = 'button',
  ...rest
}: Props) {
  const { status, run, isBusy } = useActionFeedback()

  const isSuccess = status === 'success'
  const isError = status === 'error'
  const isRunning = status === 'running'

  const toneClass = isSuccess
    ? 'border-emerald-600/35 bg-emerald-50 text-emerald-900'
    : isError
      ? 'border-red-300 bg-red-50 text-red-900'
      : ''

  const content = isSuccess ? (
    <>
      <Check className="size-3.5 shrink-0" strokeWidth={2.5} aria-hidden />
      <span>{successLabel}</span>
    </>
  ) : isError ? (
    <>
      <X className="size-3.5 shrink-0" strokeWidth={2.5} aria-hidden />
      <span>{errorLabel}</span>
    </>
  ) : isRunning ? (
    <>
      <Loader2 className="size-3.5 shrink-0 animate-spin" aria-hidden />
      <span>{runningLabel ?? 'Procesando…'}</span>
    </>
  ) : (
    children
  )

  return (
    <button
      type={type}
      className={`du-pill-action inline-flex items-center justify-center gap-1.5 transition-colors ${toneClass} ${className}`}
      disabled={disabled || isBusy}
      aria-busy={isRunning}
      onClick={() => void run(onAction)}
      {...rest}
    >
      {content}
    </button>
  )
}

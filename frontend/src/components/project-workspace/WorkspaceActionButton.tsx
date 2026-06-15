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

const PRIMARY_BASE =
  'inline-flex items-center justify-center gap-2 rounded-md px-5 py-2.5 text-base font-semibold uppercase tracking-wide text-white shadow-sm outline-none transition-[opacity,transform,box-shadow,background-color] duration-150 hover:opacity-[0.92] active:translate-y-px active:opacity-100 active:shadow-inner disabled:cursor-not-allowed disabled:opacity-50 disabled:active:translate-y-0 focus-visible:ring-2 focus-visible:ring-primary/45 focus-visible:ring-offset-2 focus-visible:ring-offset-white'

export function WorkspaceActionButton({
  children,
  onAction,
  successLabel = 'Guardado',
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
    ? 'bg-emerald-600 hover:opacity-95'
    : isError
      ? 'bg-red-700 hover:opacity-95'
      : 'bg-primary'

  const content = isSuccess ? (
    <>
      <Check className="size-4 shrink-0" strokeWidth={2.5} aria-hidden />
      <span>{successLabel}</span>
    </>
  ) : isError ? (
    <>
      <X className="size-4 shrink-0" strokeWidth={2.5} aria-hidden />
      <span>{errorLabel}</span>
    </>
  ) : isRunning ? (
    <>
      <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden />
      <span>{runningLabel ?? 'Procesando…'}</span>
    </>
  ) : (
    children
  )

  return (
    <button
      type={type}
      className={`${PRIMARY_BASE} ${toneClass} ${className}`}
      disabled={disabled || isBusy}
      aria-busy={isRunning}
      onClick={() => void run(onAction)}
      {...rest}
    >
      {content}
    </button>
  )
}

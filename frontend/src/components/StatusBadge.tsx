type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

type Props = {
  status: SaveStatus
  lastSavedAt: string | null
  errorMessage: string | null
}

function labelFor(status: SaveStatus): string {
  if (status === 'saving') return 'Guardando…'
  if (status === 'saved') return 'Guardado'
  if (status === 'error') return 'Error al guardar'
  return 'Listo'
}

export function StatusBadge({ status, lastSavedAt, errorMessage }: Props) {
  const tone =
    status === 'error'
      ? 'border-primary/30 bg-primary/5 text-primary'
      : status === 'saving'
        ? 'border-black/10 bg-black/[0.03] text-ink'
        : status === 'saved'
          ? 'border-emerald-700/20 bg-emerald-50 text-emerald-900'
          : 'border-black/10 bg-white text-muted'

  return (
    <div className="flex flex-col items-end gap-1 text-right sm:items-start sm:text-left">
      <span
        className={`inline-flex items-center rounded-md border px-3 py-1.5 text-sm font-medium ${tone}`}
        role="status"
        aria-live="polite"
      >
        {labelFor(status)}
        {lastSavedAt && status !== 'error' ? (
          <span className="ml-1.5 font-normal text-muted">
            · {new Date(lastSavedAt).toLocaleString()}
          </span>
        ) : null}
      </span>
      {errorMessage ? <span className="max-w-xs text-sm text-primary">{errorMessage}</span> : null}
    </div>
  )
}

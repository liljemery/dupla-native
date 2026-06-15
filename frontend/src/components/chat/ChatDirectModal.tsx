import { formatPersonFullName } from '../../lib/personDisplay'
import { PrimaryButton } from '../PrimaryButton'

type ChatDirectModalProps = {
  open: boolean
  dmTarget: string
  setDmTarget: React.Dispatch<React.SetStateAction<string>>
  directory: { uuid: string; email: string; first_name: string; last_name: string }[]
  error: string | null
  onBackdropClose: () => void
  onCancel: () => void
  onSubmit: () => void
}

export function ChatDirectModal({
  open,
  dmTarget,
  setDmTarget,
  directory,
  error,
  onBackdropClose,
  onCancel,
  onSubmit,
}: ChatDirectModalProps) {
  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onBackdropClose()
      }}
    >
      <div
        className="w-full max-w-md rounded-lg border border-black/10 bg-white p-6 shadow-lg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dm-modal-title"
      >
        <h2 id="dm-modal-title" className="text-lg font-semibold text-ink">
          Chat con una persona
        </h2>
        <p className="du-meta mt-1">Se abre un hilo privado entre tú y la persona elegida.</p>
        <label className="du-label mt-4 block" htmlFor="dm-user">
          Usuario
        </label>
        <select
          id="dm-user"
          className="du-input mt-1 w-full"
          value={dmTarget}
          onChange={(e) => setDmTarget(e.target.value)}
        >
          <option value="">Selecciona…</option>
          {directory.map((u) => (
            <option key={u.uuid} value={u.uuid}>
              {formatPersonFullName(u.first_name, u.last_name, u.email)}
            </option>
          ))}
        </select>
        {error ? <p className="mt-2 text-sm text-primary">{error}</p> : null}
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink"
            onClick={onCancel}
          >
            Cancelar
          </button>
          <PrimaryButton type="button" disabled={!dmTarget} onClick={() => void onSubmit()}>
            Abrir chat
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}

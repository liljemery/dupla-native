import { formatPersonFullName } from '../../lib/personDisplay'
import { PrimaryButton } from '../PrimaryButton'

type DirUser = { uuid: string; email: string; first_name: string; last_name: string }

type ChatGroupModalProps = {
  open: boolean
  groupTitle: string
  setGroupTitle: React.Dispatch<React.SetStateAction<string>>
  groupMemberSearch: string
  setGroupMemberSearch: React.Dispatch<React.SetStateAction<string>>
  groupSelectedUuids: string[]
  directory: DirUser[]
  groupPickerCandidates: DirUser[]
  error: string | null
  onBackdropClose: () => void
  onCancel: () => void
  onAddMember: (uuid: string) => void
  onRemoveMember: (uuid: string) => void
  onCreateGroup: () => void
}

export function ChatGroupModal({
  open,
  groupTitle,
  setGroupTitle,
  groupMemberSearch,
  setGroupMemberSearch,
  groupSelectedUuids,
  directory,
  groupPickerCandidates,
  error,
  onBackdropClose,
  onCancel,
  onAddMember,
  onRemoveMember,
  onCreateGroup,
}: ChatGroupModalProps) {
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
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-lg border border-black/10 bg-white p-6 shadow-lg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="group-modal-title"
      >
        <h2 id="group-modal-title" className="text-lg font-semibold text-ink">
          Nuevo grupo
        </h2>
        <p className="du-meta mt-1">Tú quedas incluido automáticamente. Elige al menos un miembro más.</p>
        <label className="du-label mt-4 block" htmlFor="group-title">
          Nombre del grupo
        </label>
        <input
          id="group-title"
          className="du-input mt-1 w-full"
          value={groupTitle}
          onChange={(e) => setGroupTitle(e.target.value)}
          maxLength={120}
        />
        <div className="du-label mt-4">Miembros</div>
        <p className="mt-1 text-xs text-muted">
          Busca por correo y elige de la lista para añadir. Puedes quitar miembros con la ×.
        </p>
        <label className="du-label mt-3 block" htmlFor="group-member-search">
          Buscar usuario
        </label>
        <input
          id="group-member-search"
          type="search"
          autoComplete="off"
          className="du-input mt-1 w-full"
          placeholder="Escribe para filtrar…"
          value={groupMemberSearch}
          onChange={(e) => setGroupMemberSearch(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && groupPickerCandidates[0]) {
              e.preventDefault()
              onAddMember(groupPickerCandidates[0].uuid)
            }
          }}
        />
        {groupSelectedUuids.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {groupSelectedUuids.map((id) => {
              const du = directory.find((u) => u.uuid === id)
              const label = du ? formatPersonFullName(du.first_name, du.last_name, du.email) : id
              return (
                <span
                  key={id}
                  className="inline-flex max-w-full items-center gap-1 rounded-full border border-primary/30 bg-primary/[0.08] py-1 pl-2.5 pr-1 text-xs text-ink"
                >
                  <span className="truncate">{label}</span>
                  <button
                    type="button"
                    className="shrink-0 rounded-full px-1.5 py-0.5 text-muted hover:bg-black/10 hover:text-ink"
                    aria-label={`Quitar ${label}`}
                    onClick={() => onRemoveMember(id)}
                  >
                    ×
                  </button>
                </span>
              )
            })}
          </div>
        ) : (
          <p className="mt-2 text-xs text-muted">Nadie añadido aún.</p>
        )}
        <div className="du-label mt-3">Resultados</div>
        <ul
          className="mt-1 max-h-48 overflow-y-auto rounded-md border border-black/10 bg-white p-1 shadow-inner"
          role="listbox"
          aria-label="Usuarios disponibles"
        >
          {groupPickerCandidates.length === 0 ? (
            <li className="px-2 py-3 text-center text-sm text-muted">
              {directory.length === 0
                ? 'No hay usuarios en el directorio.'
                : 'Sin coincidencias o todos ya están en el grupo.'}
            </li>
          ) : (
            groupPickerCandidates.map((u) => (
              <li key={u.uuid}>
                <button
                  type="button"
                  role="option"
                  className="w-full rounded px-2 py-2 text-left text-sm text-ink hover:bg-primary/[0.08]"
                  onClick={() => onAddMember(u.uuid)}
                >
                  {formatPersonFullName(u.first_name, u.last_name, u.email)}
                </button>
              </li>
            ))
          )}
        </ul>
        {error ? <p className="mt-2 text-sm text-primary">{error}</p> : null}
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink"
            onClick={onCancel}
          >
            Cancelar
          </button>
          <PrimaryButton type="button" onClick={() => void onCreateGroup()}>
            Crear grupo
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}

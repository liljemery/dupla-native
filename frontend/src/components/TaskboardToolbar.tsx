import { Plus } from 'lucide-react'

import { PrimaryButton } from './PrimaryButton'

type TaskboardToolbarProps = {
  embedded: boolean
  showAddTask: boolean
  onAddTask: () => void
  boardSearch: string
  setBoardSearch: React.Dispatch<React.SetStateAction<string>>
  includeArchived: boolean
  setIncludeArchived: React.Dispatch<React.SetStateAction<boolean>>
}

export function TaskboardToolbar({
  embedded,
  showAddTask,
  onAddTask,
  boardSearch,
  setBoardSearch,
  includeArchived,
  setIncludeArchived,
}: TaskboardToolbarProps) {
  return (
    <div
      data-tour="taskboard-toolbar"
      className={`flex shrink-0 flex-col gap-2 rounded-lg border border-black/8 bg-white px-2 py-2 shadow-sm sm:flex-row sm:items-center sm:gap-3 sm:px-3 ${embedded ? '' : 'gap-3 px-3 py-3 sm:gap-4 sm:px-4'}`}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-2 sm:max-w-none sm:flex-row sm:items-center sm:gap-2">
        <div className="relative min-w-0 flex-1 sm:max-w-sm">
          <svg
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.75}
            stroke="currentColor"
            aria-hidden
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z"
            />
          </svg>
          <input
            type="search"
            value={boardSearch}
            onChange={(e) => setBoardSearch(e.target.value)}
            placeholder="Buscar tareas…"
            className="du-input h-9 w-full rounded-md border-black/10 bg-white py-0 pl-9 pr-3 text-sm placeholder:text-muted/90 focus:border-primary/35 focus:ring-1 focus:ring-primary/25"
            aria-label="Buscar tareas"
          />
        </div>
        {showAddTask ? (
          <PrimaryButton
            type="button"
            className="h-9 shrink-0 gap-1.5 px-3 py-0 text-xs font-semibold normal-case tracking-normal"
            onClick={onAddTask}
          >
            <Plus className="h-3.5 w-3.5 shrink-0" strokeWidth={2.5} aria-hidden />
            Añadir tarea
          </PrimaryButton>
        ) : null}
      </div>

      <div className="flex min-w-0 flex-wrap items-center gap-2 sm:justify-end sm:gap-3">
        <p className="max-w-md text-xs text-muted">
          Solo ves las tareas asignadas a tu cuenta (o creadas por ti sin asignar).
        </p>
        <button
          type="button"
          aria-pressed={includeArchived}
          onClick={() => setIncludeArchived((v) => !v)}
          className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
            includeArchived
              ? 'border-primary/35 bg-primary/12 text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.6)]'
              : 'border-black/10 bg-white text-ink hover:border-black/18 hover:bg-black/[0.03]'
          }`}
        >
          Archivadas
        </button>
      </div>
    </div>
  )
}

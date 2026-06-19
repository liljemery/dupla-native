import { ProjectFolderCard } from './ProjectFolderCard'
import type { Project } from '../../types/project'

type ProjectsMasterListProps = {
  projects: Project[]
  loadingList: boolean
  totalCount: number
  searchQuery: string
  menuUuid: string | null
  onOpen: (uuid: string) => void
  onMenuToggle: (uuid: string | null) => void
}

export function ProjectsMasterList({
  projects,
  loadingList,
  totalCount,
  searchQuery,
  menuUuid,
  onOpen,
  onMenuToggle,
}: ProjectsMasterListProps) {
  if (loadingList) {
    return (
      <p className="py-12 text-center text-sm text-muted">Cargando proyectos…</p>
    )
  }

  if (totalCount === 0) {
    return (
      <p className="py-12 text-center text-sm text-muted">
        Todavía no hay proyectos en tu cuenta.
      </p>
    )
  }

  if (projects.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-muted">
        {searchQuery.trim()
          ? `Ningún resultado para «${searchQuery.trim()}» con este filtro.`
          : 'Ningún proyecto con este filtro.'}
      </p>
    )
  }

  return (
    <ul className="du-projects-folder-grid" data-tour="projects-board">
      {projects.map((p) => (
        <li key={p.uuid}>
          <ProjectFolderCard
            project={p}
            menuOpen={menuUuid === p.uuid}
            onOpen={() => onOpen(p.uuid)}
            onMenuToggle={() => onMenuToggle(menuUuid === p.uuid ? null : p.uuid)}
          />
        </li>
      ))}
    </ul>
  )
}

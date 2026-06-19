import { useEffect, useMemo, useState } from 'react'
import { Search } from 'lucide-react'

import { FilterBar, FilterChip } from '../ui/FilterBar'
import { ProjectsMasterList } from './ProjectsMasterList'
import type { DashboardStatusFilter } from '../../lib/projectDashboardBuckets'
import type { Project } from '../../types/project'

type ProjectsDashboardOverviewProps = {
  loadingList: boolean
  projects: Project[]
  displayProjects: Project[]
  projectSearch: string
  onProjectSearchChange: (q: string) => void
  statusFilter: DashboardStatusFilter
  onStatusFilter: (f: DashboardStatusFilter) => void
  stats: { total: number; proceso: number; revision: number; cerrados: number }
  onOpenProject: (uuid: string) => void
}

export function ProjectsDashboardOverview({
  loadingList,
  projects,
  displayProjects,
  projectSearch,
  onProjectSearchChange,
  statusFilter,
  onStatusFilter,
  stats,
  onOpenProject,
}: ProjectsDashboardOverviewProps) {
  const [menuUuid, setMenuUuid] = useState<string | null>(null)

  const chips: { id: DashboardStatusFilter; label: string; count: number }[] = useMemo(
    () => [
      { id: 'todos', label: 'Todos', count: stats.total },
      { id: 'proceso', label: 'En proceso', count: stats.proceso },
      { id: 'revision', label: 'En revisión', count: stats.revision },
      { id: 'cerrado', label: 'Cerrado', count: stats.cerrados },
    ],
    [stats],
  )

  useEffect(() => {
    if (!menuUuid) return
    const onDoc = () => setMenuUuid(null)
    document.addEventListener('click', onDoc)
    return () => document.removeEventListener('click', onDoc)
  }, [menuUuid])

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 pb-4">
      <FilterBar
        search={
          <label className="relative block" data-tour="projects-search">
            <span className="sr-only">Buscar proyectos</span>
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
              strokeWidth={2}
              aria-hidden
            />
            <input
              type="search"
              className="du-input h-9 w-full rounded-full border-slate-200 bg-slate-50 py-0 pl-9 pr-3 text-sm placeholder:text-muted/90 focus-visible:bg-white"
              placeholder="Buscar proyectos…"
              value={projectSearch}
              onChange={(e) => onProjectSearchChange(e.target.value)}
              autoComplete="off"
              aria-label="Buscar proyectos"
            />
          </label>
        }
      >
        {chips.map((c) => (
          <FilterChip
            key={c.id}
            label={c.label}
            count={c.count}
            active={statusFilter === c.id}
            onClick={() => onStatusFilter(c.id)}
          />
        ))}
      </FilterBar>

      <div className="du-master-detail-shell">
        <ProjectsMasterList
            projects={displayProjects}
            loadingList={loadingList}
            totalCount={projects.length}
            searchQuery={projectSearch}
            menuUuid={menuUuid}
            onOpen={onOpenProject}
            onMenuToggle={setMenuUuid}
          />
      </div>
    </div>
  )
}

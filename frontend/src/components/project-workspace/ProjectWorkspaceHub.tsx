import {
  ClipboardCheck,
  FolderOpen,
  GitBranch,
  History,
  Info,
  LayoutGrid,
  ScrollText,
  SearchCheck,
  Truck,
  type LucideIcon,
} from 'lucide-react'

import { PROJECT_WORKSPACE_HUB_DESCRIPTIONS } from '../../constants/projectWorkspaceHubCards'
import type { WorkspaceTabItem } from './WorkspaceTabsLayout'

const HUB_CARD_ICONS: Record<string, LucideIcon> = {
  detalles: Info,
  flujo: GitBranch,
  archivos: FolderOpen,
  entregaPlanos: Truck,
  revisiones: ClipboardCheck,
  hallazgos: SearchCheck,
  pliego: ScrollText,
  eventos: History,
}

type ProjectWorkspaceHubProps = {
  sectionTabs: WorkspaceTabItem[]
  onOpenSection: (tabId: string) => void
}

export function ProjectWorkspaceHub({ sectionTabs, onOpenSection }: ProjectWorkspaceHubProps) {
  return (
    <div data-tour="workspace-tab-nav" className="flex min-h-0 min-w-0 flex-1 flex-col gap-4">
      <div className="shrink-0">
        <div className="flex items-center gap-2 text-ink">
          <LayoutGrid className="h-5 w-5 shrink-0 text-primary" aria-hidden />
          <h3 className="text-base font-semibold tracking-tight">Secciones del proyecto</h3>
        </div>
        <p className="mt-1 text-sm text-muted">Elige un área para trabajar.</p>
      </div>
      <ul className="grid min-h-0 flex-1 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {sectionTabs.map((t) => {
          const Icon = HUB_CARD_ICONS[t.id] ?? LayoutGrid
          const desc = PROJECT_WORKSPACE_HUB_DESCRIPTIONS[t.id] ?? ''
          return (
            <li key={t.id} className="min-w-0">
              <button
                type="button"
                onClick={() => onOpenSection(t.id)}
                className="flex h-full w-full flex-col gap-2 rounded-xl border border-black/10 bg-white p-4 text-left shadow-sm transition hover:border-primary/30 hover:bg-primary/[0.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary/40"
              >
                <span className="flex items-center gap-2 font-semibold text-ink">
                  <Icon className="h-5 w-5 shrink-0 text-primary" aria-hidden />
                  {t.label}
                </span>
                {desc ? <span className="text-sm leading-snug text-muted">{desc}</span> : null}
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

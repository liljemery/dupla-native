import { type ReactNode } from 'react'
import {
  ArrowLeft,
  Calculator,
  ClipboardCheck,
  FolderOpen,
  GitBranch,
  History,
  LayoutGrid,
  ScrollText,
  type LucideIcon,
} from 'lucide-react'

export type WorkspaceTabItem = { id: string; label: string }

const WORKSPACE_TAB_ICONS: Record<string, LucideIcon> = {
  hub: LayoutGrid,
  flujo: GitBranch,
  planosHallazgos: FolderOpen,
  revisiones: ClipboardCheck,
  pliego: ScrollText,
  presupuesto: Calculator,
  eventos: History,
}

function WorkspaceSectionHeaderIcon({ tabId }: { tabId: string }) {
  const Icon = WORKSPACE_TAB_ICONS[tabId]
  if (!Icon) return null
  return <Icon className="h-5 w-5 shrink-0 text-primary sm:h-6 sm:w-6" aria-hidden />
}

const workspaceTabNavClassName =
  'flex shrink-0 flex-wrap items-center gap-3 rounded-2xl border border-black/10 bg-white px-4 py-3 shadow-(--shadow-card)'

const workspaceTabBackButtonClassName =
  'inline-flex items-center gap-2 rounded-xl border border-black/12 bg-white px-3 py-2 text-sm font-semibold text-primary shadow-sm outline-none transition-colors hover:bg-primary/6 focus-visible:ring-2 focus-visible:ring-primary/35 focus-visible:ring-offset-2'

const workspaceTabPanelClassName =
  'rounded-2xl border border-black/10 bg-white p-4 shadow-(--shadow-card) sm:p-5'

type Props = {
  tabs: WorkspaceTabItem[]
  activeId: string
  onSelect: (id: string) => void
  labelledBy?: string
  children: ReactNode
}

export function WorkspaceTabsLayout({
  tabs,
  activeId,
  onSelect,
  labelledBy,
  children,
}: Props) {
  const active = tabs.find((t) => t.id === activeId)
  const isHub = activeId === 'hub'

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      {!isHub && active ? (
        <div
          data-tour="workspace-tab-nav"
          className={workspaceTabNavClassName}
          role="region"
          aria-label="Volver al inicio y título de sección"
        >
          <button
            type="button"
            className={workspaceTabBackButtonClassName}
            id={labelledBy ? `${labelledBy}-back` : undefined}
            aria-label="Volver al inicio del proyecto"
            onClick={() => onSelect('hub')}
          >
            <ArrowLeft className="h-4 w-4 shrink-0" aria-hidden />
            Volver al inicio
          </button>
          <h2
            className="flex min-w-0 flex-1 items-center gap-2 text-lg font-semibold tracking-tight text-ink sm:text-xl"
            id={`tab-heading-${active.id}`}
          >
            <WorkspaceSectionHeaderIcon tabId={active.id} />
            <span className="min-w-0">{active.label}</span>
          </h2>
        </div>
      ) : null}
      <div
        data-tour="workspace-tab-panel"
        role="tabpanel"
        aria-labelledby={!isHub && active ? `tab-heading-${active.id}` : labelledBy}
        className={`flex min-h-0 flex-1 flex-col overflow-y-auto ${isHub ? 'px-0 py-0' : 'px-0 py-4 sm:py-5'}`}
      >
        {!isHub ? (
          <div className={workspaceTabPanelClassName}>
            {children}
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  )
}

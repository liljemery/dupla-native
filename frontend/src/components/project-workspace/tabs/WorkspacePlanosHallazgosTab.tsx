import type { Project } from '../../../types/project'
import type { TechnicalFindingRow } from '../../../types/projectWorkspace'
import { WorkspaceSectionSwitch } from '../WorkspaceSectionSwitch'
import { WorkspaceArchivosTab } from './WorkspaceArchivosTab'
import { WorkspaceHallazgosTab } from './WorkspaceHallazgosTab'

type Props = {
  section: string
  onSectionChange: (section: string) => void
  viewBudget: boolean
  project: Project | null
  projectUuid: string
  token: string | null
  workflowPhase: string
  flowMsg: string | null
  findings: TechnicalFindingRow[]
  onRefreshFindings: () => Promise<void>
  onContinueToPliego: () => void
}

export function WorkspacePlanosHallazgosTab({
  section,
  onSectionChange,
  viewBudget,
  project,
  projectUuid,
  token,
  workflowPhase,
  flowMsg,
  findings,
  onRefreshFindings,
  onContinueToPliego,
}: Props) {
  const activeSection = section === 'hallazgos' && viewBudget ? 'hallazgos' : 'planos'
  const sections = viewBudget
    ? [
        { id: 'planos', label: 'Planos' },
        { id: 'hallazgos', label: 'Hallazgos' },
      ]
    : [{ id: 'planos', label: 'Planos' }]

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6">
      {viewBudget ? (
        <WorkspaceSectionSwitch
          sections={sections}
          value={activeSection}
          onChange={onSectionChange}
          ariaLabel="Secciones de planos y hallazgos"
        />
      ) : null}
      {activeSection === 'planos' ? (
        <WorkspaceArchivosTab
          projectUuid={projectUuid}
          token={token}
          workflowPhase={workflowPhase}
          flowMsg={flowMsg}
        />
      ) : (
        <WorkspaceHallazgosTab
          project={project}
          projectUuid={projectUuid}
          token={token}
          findings={findings}
          onRefresh={onRefreshFindings}
          onContinueToPliego={onContinueToPliego}
        />
      )}
    </div>
  )
}

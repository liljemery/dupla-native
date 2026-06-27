import type { PlanDeliveryRow } from '../../../types/planDelivery'
import type { RevisionRow } from '../../../types/projectWorkspace'
import { WorkspaceSectionSwitch } from '../WorkspaceSectionSwitch'
import { WorkspaceEntregaPlanosTab } from './WorkspaceEntregaPlanosTab'
import { WorkspaceRevisionesTab } from './WorkspaceRevisionesTab'

type Props = {
  section: string
  onSectionChange: (section: string) => void
  flowMsg: string | null
  revDecision: string
  setRevDecision: React.Dispatch<React.SetStateAction<string>>
  revNotes: string
  setRevNotes: React.Dispatch<React.SetStateAction<string>>
  revisions: RevisionRow[]
  onSubmitRevision: () => boolean | void | Promise<boolean | void>
  projectUuid: string
  token: string | null
  planDeliveryRows: PlanDeliveryRow[]
  planDeliveryMsg: string | null
  setPlanDeliveryRows: React.Dispatch<React.SetStateAction<PlanDeliveryRow[]>>
  onAddRow: (payload?: { description?: string; request_date?: string | null }) => boolean | Promise<boolean>
  onPatchRow: (rowUuid: string, patch: Record<string, unknown>) => void
  onDeleteRow: (rowUuid: string) => void
}

const SECTIONS = [
  { id: 'revisiones', label: 'Revisiones' },
  { id: 'entregas', label: 'Control de entregas' },
]

export function WorkspaceRevisionesEntregasTab({
  section,
  onSectionChange,
  flowMsg,
  revDecision,
  setRevDecision,
  revNotes,
  setRevNotes,
  revisions,
  onSubmitRevision,
  projectUuid,
  token,
  planDeliveryRows,
  planDeliveryMsg,
  setPlanDeliveryRows,
  onAddRow,
  onPatchRow,
  onDeleteRow,
}: Props) {
  const activeSection = section === 'entregas' ? 'entregas' : 'revisiones'

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6">
      <WorkspaceSectionSwitch
        sections={SECTIONS}
        value={activeSection}
        onChange={onSectionChange}
        ariaLabel="Secciones de revisiones y entregas"
      />
      {activeSection === 'revisiones' ? (
        <WorkspaceRevisionesTab
          flowMsg={flowMsg}
          revDecision={revDecision}
          setRevDecision={setRevDecision}
          revNotes={revNotes}
          setRevNotes={setRevNotes}
          revisions={revisions}
          onSubmitRevision={onSubmitRevision}
        />
      ) : (
        <WorkspaceEntregaPlanosTab
          projectUuid={projectUuid}
          token={token}
          planDeliveryRows={planDeliveryRows}
          planDeliveryMsg={planDeliveryMsg}
          setPlanDeliveryRows={setPlanDeliveryRows}
          onAddRow={onAddRow}
          onPatchRow={onPatchRow}
          onDeleteRow={onDeleteRow}
        />
      )}
    </div>
  )
}

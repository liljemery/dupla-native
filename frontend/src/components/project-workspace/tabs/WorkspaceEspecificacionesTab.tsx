import { canApproveSpecifications, canViewBudget } from '../../../lib/accessPermissions'
import {
  isConstructionPliegoSchemaActive,
} from '../../../lib/constructionPliegoState'
import { useAuthStore } from '../../../store/authStore'
import type { Project } from '../../../types/project'
import type { ConstructionLineValue } from '../../../types/constructionPliego'
import { BusinessPliegoForm } from '../../BusinessPliegoForm'
import { PliegoCondicionesForm } from '../../PliegoCondicionesForm'
import { PliegoSideRail } from '../PliegoSideRail'
import type { PliegoItemState } from '../../../types/pliegoForm'

type WorkspaceEspecificacionesTabProps = {
  project: Project | null
  projectUuid: string
  projectDisplayName: string
  token: string | null
  role: string | null
  pliegoItemStates: Record<string, PliegoItemState>
  setPliegoItemStates: React.Dispatch<React.SetStateAction<Record<string, PliegoItemState>>>
  pliegoApprovedSections: Record<string, string>
  setPliegoApprovedSections: React.Dispatch<React.SetStateAction<Record<string, string>>>
  constructionLines: Record<string, ConstructionLineValue>
  onConstructionLineChange: (idItem: string, patch: Partial<ConstructionLineValue>) => void
  constructionApprovedChapters: Record<number, string>
  setConstructionApprovedChapters: React.Dispatch<React.SetStateAction<Record<number, string>>>
  specSummary: string
  onSpecSummaryChange: (value: string) => void
  onGenerateConstruction: (force: boolean) => Promise<void>
  generateConstructionBusy: boolean
  onPersist: () => Promise<boolean | void>
  specSaveBusy: boolean
  flowMsg: string | null
  onApprovePliego: () => Promise<boolean | void>
  pliegoApproved: boolean
  pliegoReadyForApproval: boolean
  pliegoApproveBlocker: string | null
  pliegoEditable: boolean
  pliegoReadOnlyHint: string | null
  pliegoGeneratedAt: string | null
  onApproveGaFoSection: (sectionId: string) => Promise<boolean | void>
  onExportPliegoPdf?: () => void
  onExportPliegoXlsx?: () => void
  onGoPresupuesto?: () => void
}

export function WorkspaceEspecificacionesTab({
  project,
  projectUuid,
  projectDisplayName,
  token,
  role,
  pliegoItemStates,
  setPliegoItemStates,
  pliegoApprovedSections,
  setPliegoApprovedSections,
  constructionLines,
  onConstructionLineChange,
  constructionApprovedChapters,
  setConstructionApprovedChapters,
  specSummary,
  onSpecSummaryChange,
  onGenerateConstruction,
  generateConstructionBusy,
  onPersist,
  specSaveBusy,
  flowMsg,
  onApprovePliego,
  pliegoApproved,
  pliegoReadyForApproval,
  pliegoApproveBlocker,
  pliegoEditable,
  pliegoReadOnlyHint,
  pliegoGeneratedAt,
  onApproveGaFoSection,
  onExportPliegoPdf,
  onExportPliegoXlsx,
  onGoPresupuesto,
}: WorkspaceEspecificacionesTabProps) {
  const userUuid = useAuthStore((s) => s.userUuid)
  const isTeamLeader = useAuthStore((s) => s.isTeamLeader)
  const canApprove = canApproveSpecifications(role as import('../../../constants/userRoles').UserRole | null, isTeamLeader)
  const viewBudget = canViewBudget(role as import('../../../constants/userRoles').UserRole | null)
  const specDoc =
    project?.specifications_document && typeof project.specifications_document === 'object'
      ? (project.specifications_document as Record<string, unknown>)
      : undefined
  const showConstructionPliego = isConstructionPliegoSchemaActive(specDoc)

  function markGaFoSectionApproved(sectionId: string) {
    setPliegoApprovedSections((prev) => ({
      ...prev,
      [sectionId]: new Date().toISOString(),
    }))
  }

  function approveGaFoSectionFromRail(sectionId: string) {
    void onApproveGaFoSection(sectionId)
  }

  function clearGaFoSectionApproval(sectionId: string) {
    setPliegoApprovedSections((prev) => {
      if (!prev[sectionId]) return prev
      const next = { ...prev }
      delete next[sectionId]
      return next
    })
  }

  function approveConstructionChapter(chapterNum: number) {
    setConstructionApprovedChapters((prev) => ({
      ...prev,
      [chapterNum]: new Date().toISOString(),
    }))
  }

  function clearConstructionChapterApproval(chapterNum: number) {
    setConstructionApprovedChapters((prev) => {
      if (!prev[chapterNum]) return prev
      const next = { ...prev }
      delete next[chapterNum]
      return next
    })
  }

  return (
    <div className="flex min-h-0 flex-col gap-4">
      {!pliegoEditable && pliegoReadOnlyHint ? (
        <p className="rounded-lg border border-black/15 bg-black/4 px-4 py-3 text-sm text-ink">
          {pliegoReadOnlyHint}
        </p>
      ) : null}
      <div className="flex min-h-0 flex-col gap-6 lg:flex-row lg:items-start lg:gap-6">
      <div className="flex min-w-0 flex-1 flex-col gap-6">
        <PliegoCondicionesForm
          projectUuid={projectUuid}
          token={token}
          documentTitle={`Pliego de condiciones — ${projectDisplayName}`}
          itemStates={pliegoItemStates}
          onItemStatesChange={setPliegoItemStates}
          approvedSections={pliegoApprovedSections}
          canApproveSection={canApprove}
          editable={pliegoEditable}
          onSectionApproved={markGaFoSectionApproved}
          onClearSectionApproval={clearGaFoSectionApproval}
          onApproveSection={onApproveGaFoSection}
          onPersist={onPersist}
          persistBusy={specSaveBusy}
          flowMsg={flowMsg}
          onExportPdf={onExportPliegoPdf}
          onExportXlsx={onExportPliegoXlsx}
        />

        {showConstructionPliego ? (
          <BusinessPliegoForm
            documentTitle={`Partidas de obra — ${projectDisplayName}`}
            lineValues={constructionLines}
            onLineChange={(idItem, patch) => {
              onConstructionLineChange(idItem, patch)
              const chapterNum = Number(idItem.split('.')[0])
              if (Number.isFinite(chapterNum) && constructionApprovedChapters[chapterNum]) {
                clearConstructionChapterApproval(chapterNum)
              }
            }}
            specSummary={specSummary}
            onSpecSummaryChange={onSpecSummaryChange}
            onGenerate={onGenerateConstruction}
            generateBusy={generateConstructionBusy}
            saveBusy={specSaveBusy}
            onSave={onPersist}
            approved={pliegoApproved}
            generatedAt={pliegoGeneratedAt}
            flowMsg={flowMsg}
            approvedChapters={constructionApprovedChapters}
            canApproveChapter={canApprove}
            onApproveChapter={approveConstructionChapter}
          />
        ) : null}
      </div>

      <PliegoSideRail
        projectUuid={projectUuid}
        token={token}
        userUuid={userUuid}
        itemStates={pliegoItemStates}
        approvedSections={pliegoApprovedSections}
        approved={pliegoApproved}
        generatedAt={pliegoGeneratedAt}
        canApprove={canApprove}
        viewBudget={viewBudget}
        pliegoReadyForApproval={pliegoReadyForApproval}
        pliegoApproveBlocker={pliegoApproveBlocker}
        onApprove={onApprovePliego}
        onApproveSection={approveGaFoSectionFromRail}
        onGoPresupuesto={onGoPresupuesto}
      />
      </div>
    </div>
  )
}

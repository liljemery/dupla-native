import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { apiFetch } from '../api/client'
import { ProjectConfigModal } from '../components/ProjectConfigModal'
import {
  ProjectWorkspaceConsoleHeader,
  type WorkspaceConsoleTabId,
} from '../components/project-workspace/ProjectWorkspaceConsoleHeader'
import { ProjectWorkspaceDashboard } from '../components/project-workspace/ProjectWorkspaceDashboard'
import { ProjectWorkspaceDetailsSummary } from '../components/project-workspace/ProjectWorkspaceDetailsSummary'
import { WorkspacePlanosHallazgosTab } from '../components/project-workspace/tabs/WorkspacePlanosHallazgosTab'
import { WorkspaceRevisionesEntregasTab } from '../components/project-workspace/tabs/WorkspaceRevisionesEntregasTab'
import { WorkspaceEspecificacionesTab } from '../components/project-workspace/tabs/WorkspaceEspecificacionesTab'
import { WorkspaceEventosTab } from '../components/project-workspace/tabs/WorkspaceEventosTab'
import { WorkspaceFlujoTab } from '../components/project-workspace/tabs/WorkspaceFlujoTab'
import { WorkspacePresupuestoMaestroTab } from '../components/project-workspace/tabs/WorkspacePresupuestoMaestroTab'
import { WorkspaceTabsLayout } from '../components/project-workspace/WorkspaceTabsLayout'
import {
  BUSINESS_PLIEGO_SECTION_KEYS,
  emptyBusinessPliegoSections,
  isBusinessPliegoReady,
  parseBusinessPliegoFromSpec,
} from '../constants/businessPliego'
import { TUTORIAL_PROJECT_UUID } from '../constants/tutorialProject'
import { loadAdminDirectoryUsers } from '../lib/adminUsersDirectoryCache'
import { isValidUuidString, normalizeDirectoryUsers, type DirectoryUserRow } from '../lib/directoryUsers'
import { projectWorkspaceTabsForRole } from '../constants/projectWorkspaceTabs'
import { NEXT_WORKFLOW_PHASE } from '../constants/workflowPhases'
import { downloadBlob, filenameFromContentDisposition } from '../lib/download'
import { budgetPipeline } from '../lib/budgetPipeline'
import {
  emptyConstructionLineValues,
  isConstructionPliegoFullyComplete,
  isConstructionPliegoSchemaActive,
  parseConstructionApprovedChapters,
  parseConstructionPliegoFromSpec,
  serializeConstructionApprovedChapters,
  synthesizeBusinessSectionsFromConstruction,
} from '../lib/constructionPliegoState'
import {
  isGaFoChecklistFullyTerminal,
  markGaFoSectionItemsComplete,
  mergePliegoItemStates,
  parseGaFoApprovedSections,
  serializeGaFoApprovedSections,
  stablePliegoItemStatesSignature,
} from '../lib/pliegoFormState'
import { isPliegoReadyForApproval, buildPliegoDraftSpec, pliegoSectionsIncompleteMessage, isPliegoEditablePhase, pliegoReadOnlyMessage } from '../lib/pliegoApproval'
import { hasElevatedAccess, canViewBudget, isBudgetWorkspaceTab, workflowPhaseLabelForRole, workflowStepTitleForRole, canApproveSpecifications } from '../lib/accessPermissions'
import {
  defaultSectionForTab,
  normalizeWorkspaceRoute,
  type PresupuestoSectionId,
} from '../lib/workspaceNavigation'
import { useAuthStore } from '../store/authStore'
import type { ConstructionLineValue } from '../types/constructionPliego'
import type { PlanDeliveryRow } from '../types/planDelivery'
import type { PliegoItemState } from '../types/pliegoForm'
import type { RevisionRow, SubcontractQuoteRow, TechnicalFindingRow } from '../types/projectWorkspace'
import type { Project } from '../types/project'
import type { WorkflowTemplateDetail } from '../types/workflowTemplate'

export function ProjectWorkspacePage() {
  const navigate = useNavigate()
  const { projectUuid = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const token = useAuthStore((s) => s.token)
  const role = useAuthStore((s) => s.role)
  const permissions = useAuthStore((s) => s.permissions)
  const elevated = hasElevatedAccess(permissions)
  const viewBudget = canViewBudget(permissions)
  const canApprovePliego = canApproveSpecifications(permissions)
  const [tab, setTab] = useState<string>('hub')
  const [project, setProject] = useState<Project | null>(null)
  const [flowTemplateDetail, setFlowTemplateDetail] = useState<WorkflowTemplateDetail | null>(null)
  const [projectError, setProjectError] = useState<string | null>(null)
  const [flowMsg, setFlowMsg] = useState<string | null>(null)
  const [specSummary, setSpecSummary] = useState('')
  const [pliegoItemStates, setPliegoItemStates] = useState<Record<string, PliegoItemState>>(() =>
    mergePliegoItemStates(undefined),
  )
  const [specSaveBusy, setSpecSaveBusy] = useState(false)
  const [businessPliegoSections, setBusinessPliegoSections] = useState(() => emptyBusinessPliegoSections())
  const [constructionLines, setConstructionLines] = useState(() => emptyConstructionLineValues())
  const [constructionDirty, setConstructionDirty] = useState(false)
  const [pliegoApprovedSections, setPliegoApprovedSections] = useState<Record<string, string>>({})
  const [constructionApprovedChapters, setConstructionApprovedChapters] = useState<Record<number, string>>({})
  const [generateConstructionBusy, setGenerateConstructionBusy] = useState(false)
  const [pliegoMeta, setPliegoMeta] = useState<{ approved: boolean; generatedAt: string | null }>({
    approved: false,
    generatedAt: null,
  })
  const [revisions, setRevisions] = useState<RevisionRow[]>([])
  const [quotes, setQuotes] = useState<SubcontractQuoteRow[]>([])
  const [revDecision, setRevDecision] = useState('APPROVED')
  const [revNotes, setRevNotes] = useState('')
  const [bpDraft, setBpDraft] = useState<Record<string, unknown>>({})
  const [clientVersion, setClientVersion] = useState('')
  const [newQuoteTitle, setNewQuoteTitle] = useState('')
  const [lineItem, setLineItem] = useState('')
  const [linePrice, setLinePrice] = useState('')
  const [activeQuote, setActiveQuote] = useState('')
  const [memberRows, setMemberRows] = useState<DirectoryUserRow[]>([])
  const [adminUsers, setAdminUsers] = useState<DirectoryUserRow[]>([])
  const [membersBusy, setMembersBusy] = useState(false)
  const [membersMsg, setMembersMsg] = useState<string | null>(null)
  const [memberSelection, setMemberSelection] = useState<Set<string>>(new Set())
  const [planDeliveryRows, setPlanDeliveryRows] = useState<PlanDeliveryRow[]>([])
  const [planDeliveryMsg, setPlanDeliveryMsg] = useState<string | null>(null)
  const [findings, setFindings] = useState<TechnicalFindingRow[]>([])
  const [configOpen, setConfigOpen] = useState(false)

  const workspaceTabs = useMemo(() => projectWorkspaceTabsForRole(permissions), [permissions])

  const workspaceSection = searchParams.get('section')?.trim() ?? null

  const selectTab = useCallback(
    (id: string, section?: string) => {
      if (!canViewBudget(permissions) && isBudgetWorkspaceTab(id)) return
      setTab(id)
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          if (id === 'hub') {
            next.delete('tab')
            next.delete('section')
          } else {
            next.set('tab', id)
            const nextSection = section ?? defaultSectionForTab(id)
            if (nextSection) next.set('section', nextSection)
            else next.delete('section')
          }
          next.delete('focus')
          return next
        },
        { replace: true },
      )
    },
    [permissions, setSearchParams],
  )

  const setWorkspaceSection = useCallback(
    (section: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set('section', section)
          return next
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  const openFlujo = useCallback(() => {
    selectTab('flujo')
  }, [selectTab])

  useEffect(() => {
    if (!canViewBudget(permissions) && isBudgetWorkspaceTab(tab)) {
      setTab('hub')
    }
  }, [permissions, tab])

  useEffect(() => {
    if (!token || !project?.workflow_template_uuid) {
      setFlowTemplateDetail(null)
      return
    }
    let cancelled = false
    void (async () => {
      const res = await apiFetch(`/api/workflow-templates/${project.workflow_template_uuid}`, { token })
      if (!res.ok || cancelled) return
      setFlowTemplateDetail((await res.json()) as WorkflowTemplateDetail)
    })()
    return () => {
      cancelled = true
    }
  }, [token, project?.workflow_template_uuid])

  const templateStepProgress = useMemo(() => {
    if (!project || !flowTemplateDetail?.steps?.length) return null
    const ordered = [...flowTemplateDetail.steps].sort((a, b) => a.sort_index - b.sort_index)
    const idx = ordered.findIndex((s) => s.uuid === project.current_workflow_step_uuid)
    if (idx < 0) return null
    return { current: idx + 1, total: ordered.length }
  }, [project, flowTemplateDetail])

  const orderedTemplateSteps = useMemo(() => {
    if (!flowTemplateDetail?.steps?.length) return null
    return [...flowTemplateDetail.steps]
      .sort((a, b) => a.sort_index - b.sort_index)
      .map((s) => ({ uuid: s.uuid, title: s.title }))
  }, [flowTemplateDetail])

  const refreshProject = useCallback(async () => {
    if (!projectUuid || !token) return
    setProjectError(null)
    const res = await apiFetch(`/api/projects/${projectUuid}`, { token })
    if (!res.ok) {
      setProjectError('No se pudieron cargar los datos del proyecto')
      return
    }
    const body = (await res.json()) as Project
    setProject(body)
    const spec = body.specifications_document ?? {}
    setSpecSummary(typeof spec.summary === 'string' ? spec.summary : '')
    const ga = spec.ga_fo_01_arquitectura
    const rawPliegoStates =
      ga && typeof ga === 'object' && ga !== null && 'item_states' in ga
        ? (ga as { item_states?: Record<string, unknown> }).item_states
        : undefined
    setPliegoItemStates(mergePliegoItemStates(rawPliegoStates))
    const bpParsed = parseBusinessPliegoFromSpec(body.specifications_document)
    setBusinessPliegoSections(bpParsed.sections)
    setPliegoMeta({ approved: bpParsed.approved, generatedAt: bpParsed.generatedAt })
    setConstructionLines(
      parseConstructionPliegoFromSpec(body.specifications_document as Record<string, unknown>),
    )
    setPliegoApprovedSections(
      parseGaFoApprovedSections(body.specifications_document as Record<string, unknown>),
    )
    setConstructionApprovedChapters(
      parseConstructionApprovedChapters(body.specifications_document as Record<string, unknown>),
    )
    setConstructionDirty(false)
    setBpDraft(budgetPipeline(body.workflow_meta ?? {}))
    setClientVersion(
      typeof budgetPipeline(body.workflow_meta ?? {}).client_approved_version_label === 'string'
        ? (budgetPipeline(body.workflow_meta ?? {}).client_approved_version_label as string)
        : '',
    )
  }, [projectUuid, token])

  useEffect(() => {
    if (projectUuid === TUTORIAL_PROJECT_UUID) {
      setTab('hub')
    }
  }, [projectUuid])

  useEffect(() => {
    const raw = searchParams.get('tab')?.trim()
    const { tab: normalizedTab, section } = normalizeWorkspaceRoute(raw, searchParams.get('section'))
    if (workspaceTabs.some((t) => t.id === normalizedTab)) {
      if (!canViewBudget(permissions) && isBudgetWorkspaceTab(normalizedTab)) {
        setTab('hub')
        return
      }
      setTab(normalizedTab)
      if (section && section !== searchParams.get('section')) {
        setSearchParams(
          (prev) => {
            const next = new URLSearchParams(prev)
            next.set('section', section)
            return next
          },
          { replace: true },
        )
      }
      return
    }
    if (raw) {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.delete('tab')
          next.delete('section')
          return next
        },
        { replace: true },
      )
      setTab('hub')
    }
  }, [projectUuid, searchParams, workspaceTabs, permissions, setSearchParams])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      await refreshProject()
      if (cancelled) return
    })()
    return () => {
      cancelled = true
    }
  }, [refreshProject])

  const pliegoRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const schedulePliegoRefresh = useCallback(() => {
    if (tab !== 'pliego' || !token || !projectUuid) return
    if (pliegoRefreshTimerRef.current) clearTimeout(pliegoRefreshTimerRef.current)
    pliegoRefreshTimerRef.current = setTimeout(() => {
      pliegoRefreshTimerRef.current = null
      void refreshProject()
    }, 450)
  }, [tab, token, projectUuid, refreshProject])

  useEffect(() => {
    if (tab === 'pliego') schedulePliegoRefresh()
  }, [tab, schedulePliegoRefresh])

  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState === 'visible' && tab === 'pliego') schedulePliegoRefresh()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [tab, schedulePliegoRefresh])

  const loadAuxLists = useCallback(async () => {
    if (!token || !projectUuid) return
    const [fr, fq] = await Promise.all([
      apiFetch(`/api/projects/${projectUuid}/architecture-revisions`, { token }),
      apiFetch(`/api/projects/${projectUuid}/subcontracts`, { token }),
    ])
    if (fr.ok) setRevisions((await fr.json()) as RevisionRow[])
    if (fq.ok) setQuotes((await fq.json()) as SubcontractQuoteRow[])
  }, [token, projectUuid])

  const loadFindings = useCallback(async () => {
    if (!token || !projectUuid) return
    const res = await apiFetch(`/api/projects/${projectUuid}/technical-findings`, { token })
    if (!res.ok) return
    setFindings((await res.json()) as TechnicalFindingRow[])
  }, [token, projectUuid])

  const loadPlanDelivery = useCallback(async () => {
    if (!token || !projectUuid) return
    setPlanDeliveryMsg(null)
    const res = await apiFetch(`/api/projects/${projectUuid}/plan-delivery-requests`, { token })
    if (!res.ok) {
      setPlanDeliveryMsg('No se pudo cargar el control de entrega de planos')
      return
    }
    setPlanDeliveryRows((await res.json()) as PlanDeliveryRow[])
  }, [token, projectUuid])

  async function addPlanDeliveryRow(payload?: { description?: string; request_date?: string | null }) {
    if (!token || !projectUuid) return false
    setPlanDeliveryMsg(null)
    const body: Record<string, unknown> = {
      description: payload?.description?.trim() ?? '',
      status: 'SOLICITADO',
    }
    if (payload?.request_date) body.request_date = payload.request_date
    const res = await apiFetch(`/api/projects/${projectUuid}/plan-delivery-requests`, {
      method: 'POST',
      token,
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      setPlanDeliveryMsg('No se pudo crear la solicitud')
      return false
    }
    const row = (await res.json()) as PlanDeliveryRow
    setPlanDeliveryRows((prev) => [...prev, row])
    return true
  }

  async function patchPlanDeliveryRow(rowUuid: string, patch: Record<string, unknown>) {
    if (!token || !projectUuid) return
    const res = await apiFetch(`/api/projects/${projectUuid}/plan-delivery-requests/${rowUuid}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(patch),
    })
    if (!res.ok) {
      setPlanDeliveryMsg('No se pudo guardar el registro')
      return
    }
    const updated = (await res.json()) as PlanDeliveryRow
    setPlanDeliveryRows((prev) => prev.map((r) => (r.uuid === rowUuid ? updated : r)))
  }

  async function deletePlanDeliveryRow(rowUuid: string) {
    if (!token || !projectUuid) return
    setPlanDeliveryMsg(null)
    const res = await apiFetch(`/api/projects/${projectUuid}/plan-delivery-requests/${rowUuid}`, {
      method: 'DELETE',
      token,
    })
    if (!res.ok) {
      setPlanDeliveryMsg('No se pudo eliminar el registro')
      return
    }
    setPlanDeliveryRows((prev) => prev.filter((r) => r.uuid !== rowUuid))
  }

  useEffect(() => {
    if (!projectUuid || !token) return
    if (tab === 'planosHallazgos' || tab === 'revisiones' || tab === 'flujo') {
      void loadAuxLists()
    }
  }, [tab, projectUuid, token, loadAuxLists])

  useEffect(() => {
    if (!projectUuid || !token) return
    if (tab === 'planosHallazgos' && workspaceSection === 'hallazgos') void loadFindings()
  }, [tab, workspaceSection, projectUuid, token, loadFindings])

  useEffect(() => {
    if (tab !== 'revisiones' || workspaceSection !== 'entregas' || !projectUuid || !token) return
    void loadPlanDelivery()
  }, [tab, workspaceSection, projectUuid, token, loadPlanDelivery])

  useEffect(() => {
    const ids = new Set(workspaceTabs.map((t) => t.id))
    if (!ids.has(tab)) {
      setTab('hub')
    }
  }, [workspaceTabs, tab])

  useEffect(() => {
    if (tab === 'planosHallazgos' && workspaceSection === 'hallazgos' && !viewBudget) {
      setWorkspaceSection('planos')
    }
  }, [tab, workspaceSection, viewBudget, setWorkspaceSection])

  useEffect(() => {
    if (!token || !projectUuid) return
    if (!project || project.uuid !== projectUuid) {
      setMemberRows([])
      return
    }
    let cancelled = false
    void (async () => {
      const m = await apiFetch(`/api/projects/${projectUuid}/members`, { token })
      if (!m.ok || cancelled) return
      setMemberRows(normalizeDirectoryUsers(await m.json()))
    })()
    return () => {
      cancelled = true
    }
  }, [token, projectUuid, project])

  useEffect(() => {
    if (!token || !elevated || !projectUuid) return
    let cancelled = false
    void (async () => {
      const adminRows = await loadAdminDirectoryUsers(token, { forceRefresh: true })
      if (!cancelled && adminRows !== null) setAdminUsers(adminRows)
    })()
    return () => {
      cancelled = true
    }
  }, [token, elevated, projectUuid])

  useEffect(() => {
    if (!projectUuid) return
    if (!project || project.uuid !== projectUuid) {
      setMemberSelection(new Set())
      return
    }
    const creator = project.created_by_user_uuid
    const ids = memberRows.map((r) => r.uuid).filter(isValidUuidString)
    const next =
      creator != null && creator !== ''
        ? new Set(ids.filter((id) => id !== creator))
        : new Set(ids)
    setMemberSelection(next)
  }, [memberRows, project, projectUuid])

  async function advancePhase(): Promise<boolean> {
    if (!token || !project) return false
    const next = NEXT_WORKFLOW_PHASE[project.workflow_phase]
    if (!next) return false
    if (next === 'BUDGETING_PIPELINE') {
      const spec = project.specifications_document
      const specObj = spec && typeof spec === 'object' ? (spec as Record<string, unknown>) : undefined
      const parsed = parseBusinessPliegoFromSpec(specObj)
      const cpActive = isConstructionPliegoSchemaActive(specObj)
      const ga = specObj?.ga_fo_01_arquitectura
      const gaIsV1 = ga && typeof ga === 'object' && (ga as Record<string, unknown>).schema_version === 1
      const hasLegacyBusiness = Boolean(
        specObj?.business_pliego && typeof specObj.business_pliego === 'object',
      )
      if (constructionDirty && cpActive) {
        setFlowMsg('Guarda el pliego para registrar las partidas antes de avanzar de fase.')
        return false
      }
      if (cpActive) {
        if (!isConstructionPliegoFullyComplete(constructionLines)) {
          setFlowMsg(
            'Completa todas las partidas del pliego (unidad, cantidad y precio unitario en cada ítem) y obtené aprobación de Gerencia o Arquitectura.',
          )
          return false
        }
        if (!parsed.approved) {
          setFlowMsg('El pliego de condiciones debe estar aprobado antes de iniciar el presupuesto.')
          return false
        }
      } else if (gaIsV1) {
        if (!isGaFoChecklistFullyTerminal(pliegoItemStates)) {
          setFlowMsg(
            'Completa el checklist GA-FO-01 (cada documento en Completo o No aplica) y guarda en la pestaña Pliego.',
          )
          return false
        }
        if (!parsed.approved) {
          setFlowMsg('El pliego de condiciones debe estar aprobado antes de iniciar el presupuesto.')
          return false
        }
      } else if (hasLegacyBusiness) {
        if (!isBusinessPliegoReady(parsed.sections, parsed.approved)) {
          setFlowMsg(
            'Completa las nueve secciones del pliego (mín. 10 caracteres cada una) y obtén aprobación de Gerencia o Arquitectura.',
          )
          return false
        }
      } else if (specSummary.trim().length < 10) {
        setFlowMsg('Completa el pliego: resumen mínimo 10 caracteres o genera el pliego estructurado.')
        return false
      }
    }
    if (next === 'MANAGEMENT_APPROVAL') {
      if (!bpDraft.control_review_done) {
        setFlowMsg('Completa la revisión de Control en Presupuesto — Checklist antes de enviar a gerencia.')
        return false
      }
    }
    if (next === 'BUDGET_APPROVED') {
      const bpSaved = budgetPipeline(project.workflow_meta ?? {})
      if (!bpSaved.management_review_done) {
        setFlowMsg('Marca la revisión de Gerencia en Presupuesto — Checklist y guarda antes de avanzar.')
        return false
      }
    }
    setFlowMsg(null)
    const res = await apiFetch(`/api/projects/${projectUuid}/transitions`, {
      method: 'POST',
      token,
      body: JSON.stringify({ target_phase: next }),
    })
    const j = await res.json().catch(() => ({}))
    if (!res.ok) {
      setFlowMsg((j as { detail?: string }).detail ?? 'No se pudo avanzar la fase')
      return false
    }
    setProject(j as Project)
    await loadAuxLists()
    return true
  }

  async function saveSpecifications(overrides?: {
    pliegoItemStates?: Record<string, PliegoItemState>
    pliegoApprovedSections?: Record<string, string>
  }): Promise<boolean> {
    if (!token || !project) return false
    if (!isPliegoEditablePhase(project.workflow_phase)) {
      setFlowMsg(pliegoReadOnlyMessage(project.workflow_phase) ?? 'El pliego no es editable en esta fase.')
      return false
    }
    const itemStates = overrides?.pliegoItemStates ?? pliegoItemStates
    const approvedSections = overrides?.pliegoApprovedSections ?? pliegoApprovedSections
    setFlowMsg(null)
    setSpecSaveBusy(true)
    try {
      const prev = project.specifications_document ?? {}
      const prevRec = prev && typeof prev === 'object' ? (prev as Record<string, unknown>) : undefined
      const prevBp =
        prev && typeof prev === 'object' && 'business_pliego' in prev
          ? (prev as Record<string, unknown>).business_pliego
          : null
      const pbd = prevBp && typeof prevBp === 'object' ? (prevBp as Record<string, unknown>) : null
      const specHasCp = isConstructionPliegoSchemaActive(prevRec)
      const useConstruction = constructionDirty || specHasCp
      const hasSectionText = BUSINESS_PLIEGO_SECTION_KEYS.some(
        (k) => (businessPliegoSections[k]?.trim().length ?? 0) > 0,
      )
      const sectionsForSave = useConstruction
        ? synthesizeBusinessSectionsFromConstruction(constructionLines)
        : businessPliegoSections
      const includeBusinessPliego =
        useConstruction || (pbd != null && (pliegoMeta.generatedAt != null || hasSectionText))
      const prevGaRaw = prevRec?.ga_fo_01_arquitectura
      const prevGa =
        prevGaRaw && typeof prevGaRaw === 'object' ? (prevGaRaw as Record<string, unknown>) : null
      const serverMergedStates = mergePliegoItemStates(
        prevGa?.item_states as Record<string, unknown> | undefined,
      )
      const keepGaApproval =
        stablePliegoItemStatesSignature(itemStates) === stablePliegoItemStatesSignature(serverMergedStates) &&
        Boolean(prevGa?.approved)

      const gaBlockBase = {
        schema_version: 1 as const,
        item_states: itemStates,
        approved_sections: serializeGaFoApprovedSections(approvedSections),
      }
      const doc: Record<string, unknown> = {
        ...prev,
        summary: specSummary,
        ga_fo_01_arquitectura: keepGaApproval
          ? {
              ...gaBlockBase,
              approved: true,
              approved_at: typeof prevGa?.approved_at === 'string' ? prevGa.approved_at : null,
              approved_by_user_uuid:
                typeof prevGa?.approved_by_user_uuid === 'string' ? prevGa.approved_by_user_uuid : null,
            }
          : {
              ...gaBlockBase,
              approved: false,
              approved_at: null,
              approved_by_user_uuid: null,
            },
      }
      if (useConstruction) {
        doc.construction_pliego = {
          schema_version: 1 as const,
          lines: constructionLines,
          approved_chapters: serializeConstructionApprovedChapters(constructionApprovedChapters),
        }
      }
      if (includeBusinessPliego) {
        const gaApproved = Boolean(prevGa?.approved)
        doc.business_pliego = {
          schema_version: 1,
          sections: sectionsForSave,
          generated_at: typeof pbd?.generated_at === 'string' ? pbd.generated_at : null,
          approved: Boolean(pbd?.approved) || (keepGaApproval && gaApproved),
          approved_at:
            typeof pbd?.approved_at === 'string'
              ? pbd.approved_at
              : keepGaApproval && gaApproved && typeof prevGa?.approved_at === 'string'
                ? prevGa.approved_at
                : null,
          approved_by_user_uuid:
            typeof pbd?.approved_by_user_uuid === 'string'
              ? pbd.approved_by_user_uuid
              : keepGaApproval && gaApproved && typeof prevGa?.approved_by_user_uuid === 'string'
                ? prevGa.approved_by_user_uuid
                : null,
        }
      }
      const res = await apiFetch(`/api/projects/${projectUuid}/specifications`, {
        method: 'PUT',
        token,
        body: JSON.stringify({ document: doc }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) {
        setFlowMsg((j as { detail?: string }).detail ?? 'Error al guardar el pliego de condiciones')
        return false
      }
      const p = j as Project
      setProject(p)
      const parsed = parseBusinessPliegoFromSpec(p.specifications_document)
      setBusinessPliegoSections(parsed.sections)
      setPliegoMeta({ approved: parsed.approved, generatedAt: parsed.generatedAt })
      setConstructionLines(
        parseConstructionPliegoFromSpec(p.specifications_document as Record<string, unknown>),
      )
      setPliegoApprovedSections(
        parseGaFoApprovedSections(p.specifications_document as Record<string, unknown>),
      )
      setConstructionApprovedChapters(
        parseConstructionApprovedChapters(p.specifications_document as Record<string, unknown>),
      )
      setConstructionDirty(false)
      return true
    } finally {
      setSpecSaveBusy(false)
    }
  }

  async function generateConstructionPliego(force: boolean): Promise<void> {
    if (!token) return
    setGenerateConstructionBusy(true)
    setFlowMsg(null)
    try {
      const res = await apiFetch(`/api/projects/${projectUuid}/specifications/generate`, {
        method: 'POST',
        token,
        body: JSON.stringify({ force }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) {
        setFlowMsg((j as { detail?: string }).detail ?? 'No se pudo generar el borrador')
        return
      }
      const p = j as Project
      setProject(p)
      setConstructionLines(
        parseConstructionPliegoFromSpec(p.specifications_document as Record<string, unknown>),
      )
      setConstructionApprovedChapters(
        parseConstructionApprovedChapters(p.specifications_document as Record<string, unknown>),
      )
      setConstructionDirty(false)
    } finally {
      setGenerateConstructionBusy(false)
    }
  }

  function handleConstructionLineChange(idItem: string, patch: Partial<ConstructionLineValue>) {
    setConstructionDirty(true)
    setConstructionLines((prev) => ({
      ...prev,
      [idItem]: { ...(prev[idItem] ?? { unidad: '', cantidad: '', unitario: '' }), ...patch },
    }))
  }

  async function approveGaFoSection(sectionId: string): Promise<boolean> {
    if (!project || !isPliegoEditablePhase(project.workflow_phase)) {
      setFlowMsg(pliegoReadOnlyMessage(project?.workflow_phase) ?? 'El pliego no es editable en esta fase.')
      return false
    }
    const nextStates = markGaFoSectionItemsComplete(pliegoItemStates, sectionId)
    const nextApproved = {
      ...pliegoApprovedSections,
      [sectionId]: new Date().toISOString(),
    }
    setPliegoItemStates(nextStates)
    setPliegoApprovedSections(nextApproved)
    return saveSpecifications({
      pliegoItemStates: nextStates,
      pliegoApprovedSections: nextApproved,
    })
  }

  async function approvePliego(): Promise<boolean> {
    if (!token || !project) return false
    if (!isPliegoEditablePhase(project.workflow_phase)) {
      setFlowMsg(pliegoReadOnlyMessage(project.workflow_phase) ?? 'El pliego no es editable en esta fase.')
      return false
    }
    setFlowMsg(null)
    const specObj =
      project.specifications_document && typeof project.specifications_document === 'object'
        ? (project.specifications_document as Record<string, unknown>)
        : undefined
    const useConstruction = isConstructionPliegoSchemaActive(specObj) || constructionDirty
    const draft = buildPliegoDraftSpec(
      specObj,
      pliegoItemStates,
      constructionLines,
      useConstruction,
    )
    const blocker = pliegoSectionsIncompleteMessage(draft)
    if (blocker) {
      setFlowMsg(blocker)
      return false
    }
    const saved = await saveSpecifications()
    if (!saved) return false
    const res = await apiFetch(`/api/projects/${projectUuid}/specifications/approve`, {
      method: 'POST',
      token,
      body: JSON.stringify({}),
    })
    const j = await res.json().catch(() => ({}))
    if (!res.ok) {
      setFlowMsg((j as { detail?: string }).detail ?? 'No se pudo aprobar el pliego')
      return false
    }
    const p = j as Project
    setProject(p)
    const parsed = parseBusinessPliegoFromSpec(p.specifications_document)
    setBusinessPliegoSections(parsed.sections)
    setPliegoMeta({ approved: parsed.approved, generatedAt: parsed.generatedAt })
    setPliegoApprovedSections(
      parseGaFoApprovedSections(p.specifications_document as Record<string, unknown>),
    )
    return true
  }

  async function saveBudgetPipeline(): Promise<boolean> {
    if (!token) return false
    setFlowMsg(null)
    const bp = { ...bpDraft, client_approved_version_label: clientVersion || null }
    const res = await apiFetch(`/api/projects/${projectUuid}/workflow-meta`, {
      method: 'PATCH',
      token,
      body: JSON.stringify({ budget_pipeline: bp }),
    })
    const j = await res.json().catch(() => ({}))
    if (!res.ok) {
      setFlowMsg((j as { detail?: string }).detail ?? 'Error al guardar presupuesto')
      return false
    }
    setProject(j as Project)
    setBpDraft(budgetPipeline((j as Project).workflow_meta ?? {}))
    return true
  }

  async function submitRevision(): Promise<boolean> {
    if (!token) return false
    setFlowMsg(null)
    const res = await apiFetch(`/api/projects/${projectUuid}/architecture-revisions`, {
      method: 'POST',
      token,
      body: JSON.stringify({
        decision: revDecision,
        notes: revNotes.trim() || null,
        checklist: {},
      }),
    })
    const j = await res.json().catch(() => ({}))
    if (!res.ok) {
      setFlowMsg((j as { detail?: string }).detail ?? 'Error al registrar revisión')
      return false
    }
    setRevNotes('')
    await loadAuxLists()
    return true
  }

  async function openProjectChat() {
    if (!token) return
    const res = await apiFetch(`/api/projects/${projectUuid}/chat/conversation`, {
      method: 'POST',
      token,
    })
    const j = await res.json().catch(() => ({}))
    if (!res.ok) return
    const uuid = (j as { uuid?: string }).uuid
    if (uuid) window.location.assign(`/app/chat?conversation=${encodeURIComponent(uuid)}`)
  }

  const displayTitle = project?.name ?? 'Proyecto'

  const exportPliegoPdf = useCallback(async () => {
    if (!token || !projectUuid) return
    const res = await apiFetch(`/api/projects/${projectUuid}/exports/pliego.pdf`, { token })
    if (!res.ok) return
    const blob = await res.blob()
    downloadBlob(blob, filenameFromContentDisposition(res, `pliego-${projectUuid}.pdf`))
  }, [token, projectUuid])

  const exportPliegoXlsx = useCallback(async () => {
    if (!token || !projectUuid) return
    const res = await apiFetch(`/api/projects/${projectUuid}/exports/pliego.xlsx`, { token })
    if (!res.ok) return
    const blob = await res.blob()
    downloadBlob(blob, filenameFromContentDisposition(res, `pliego-${projectUuid}.xlsx`))
  }, [token, projectUuid])

  const phaseLabel = project
    ? project.current_step_title?.trim()
      ? workflowStepTitleForRole(project.current_step_title.trim(), permissions)
      : workflowPhaseLabelForRole(project.workflow_phase, permissions)
    : ''
  const nextPhase = project ? NEXT_WORKFLOW_PHASE[project.workflow_phase] : undefined
  const pliegoReadyForApproval = useMemo(() => {
    const spec = project?.specifications_document
    const specObj = spec && typeof spec === 'object' ? (spec as Record<string, unknown>) : undefined
    const useConstruction = isConstructionPliegoSchemaActive(specObj) || constructionDirty
    const draft = buildPliegoDraftSpec(
      specObj,
      pliegoItemStates,
      constructionLines,
      useConstruction,
    )
    return isPliegoReadyForApproval(draft)
  }, [
    project?.specifications_document,
    pliegoItemStates,
    constructionLines,
    constructionDirty,
  ])
  const pliegoApproveBlocker = useMemo(() => {
    const spec = project?.specifications_document
    const specObj = spec && typeof spec === 'object' ? (spec as Record<string, unknown>) : undefined
    const useConstruction = isConstructionPliegoSchemaActive(specObj) || constructionDirty
    const draft = buildPliegoDraftSpec(
      specObj,
      pliegoItemStates,
      constructionLines,
      useConstruction,
    )
    return pliegoSectionsIncompleteMessage(draft)
  }, [
    project?.specifications_document,
    pliegoItemStates,
    constructionLines,
    constructionDirty,
  ])
  const pliegoEditable = isPliegoEditablePhase(project?.workflow_phase)
  const pliegoReadOnlyHint = pliegoReadOnlyMessage(project?.workflow_phase)

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
      <ProjectWorkspaceConsoleHeader
        displayTitle={displayTitle}
        projectUuid={projectUuid}
        token={token}
        tab={tab}
        onSelectTab={(id: WorkspaceConsoleTabId) => selectTab(id)}
        onOpenConfig={() => setConfigOpen(true)}
        viewBudget={viewBudget}
        phaseLabel={phaseLabel}
        clientName={project?.client_name}
        deadline={project?.deadline}
      />

      {tab === 'hub' && project ? (
        <ProjectWorkspaceDashboard
          project={project}
          projectUuid={projectUuid}
          token={token}
          phaseLabel={phaseLabel}
          bpDraft={bpDraft}
          templateStepProgress={templateStepProgress}
          orderedTemplateSteps={orderedTemplateSteps}
          flowMsg={flowMsg}
          nextPhase={nextPhase}
          role={role}
          viewBudget={viewBudget}
          memberRows={memberRows}
          quotesCount={quotes.length}
          onAdvancePhase={advancePhase}
          onOpenChat={() => void openProjectChat()}
          onOpenTab={(id, section) => selectTab(id, section)}
          onOpenFlujo={openFlujo}
          pliegoApproved={pliegoMeta.approved}
          pliegoReadyForApproval={pliegoReadyForApproval}
          canApprovePliego={canApprovePliego}
          onApprovePliego={approvePliego}
          detailsSummary={
            <ProjectWorkspaceDetailsSummary
              project={project}
              phaseLabel={phaseLabel}
              token={token}
              onOpenChat={() => void openProjectChat()}
            />
          }
        />
      ) : null}

      {tab !== 'hub' ? (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <WorkspaceTabsLayout tabs={workspaceTabs} activeId={tab} onSelect={selectTab} labelledBy="workspace-heading">
          {tab === 'flujo' ? (
            <WorkspaceFlujoTab
              project={project}
              projectUuid={projectUuid}
              token={token}
              phaseLabel={phaseLabel}
              templateStepProgress={templateStepProgress}
              orderedTemplateSteps={orderedTemplateSteps}
              flowMsg={flowMsg}
              nextPhase={nextPhase}
              onAdvancePhase={advancePhase}
              pliegoApproved={pliegoMeta.approved}
              pliegoReadyForApproval={pliegoReadyForApproval}
              canApprovePliego={canApprovePliego}
              onApprovePliego={approvePliego}
              onOpenPliego={() => selectTab('pliego')}
              onOpenPresupuesto={() => selectTab('presupuesto', 'presupuesto')}
            />
          ) : null}

          {tab === 'planosHallazgos' ? (
            <WorkspacePlanosHallazgosTab
              section={workspaceSection ?? 'planos'}
              onSectionChange={setWorkspaceSection}
              viewBudget={viewBudget}
              project={project}
              projectUuid={projectUuid}
              token={token}
              workflowPhase={project?.workflow_phase ?? 'AWAITING_FILES'}
              flowMsg={flowMsg}
              findings={findings}
              onRefreshFindings={loadFindings}
              onContinueToPliego={() => selectTab('pliego')}
            />
          ) : null}

          {tab === 'revisiones' ? (
            <WorkspaceRevisionesEntregasTab
              section={workspaceSection ?? 'revisiones'}
              onSectionChange={setWorkspaceSection}
              flowMsg={flowMsg}
              revDecision={revDecision}
              setRevDecision={setRevDecision}
              revNotes={revNotes}
              setRevNotes={setRevNotes}
              revisions={revisions}
              onSubmitRevision={submitRevision}
              projectUuid={projectUuid}
              token={token}
              planDeliveryRows={planDeliveryRows}
              planDeliveryMsg={planDeliveryMsg}
              setPlanDeliveryRows={setPlanDeliveryRows}
              onAddRow={async (payload) => {
                await addPlanDeliveryRow(payload)
                return true
              }}
              onPatchRow={(rowUuid, patch) => void patchPlanDeliveryRow(rowUuid, patch)}
              onDeleteRow={(rowUuid) => void deletePlanDeliveryRow(rowUuid)}
            />
          ) : null}

          {viewBudget && tab === 'presupuesto' ? (
            <WorkspacePresupuestoMaestroTab
              project={project}
              projectUuid={projectUuid}
              token={token}
              role={role}
              bpDraft={bpDraft}
              setBpDraft={setBpDraft}
              clientVersion={clientVersion}
              setClientVersion={setClientVersion}
              onSaveBudgetPipeline={saveBudgetPipeline}
              newQuoteTitle={newQuoteTitle}
              setNewQuoteTitle={setNewQuoteTitle}
              activeQuote={activeQuote}
              setActiveQuote={setActiveQuote}
              lineItem={lineItem}
              setLineItem={setLineItem}
              linePrice={linePrice}
              setLinePrice={setLinePrice}
              quotes={quotes}
              onLoadAuxLists={loadAuxLists}
              section={(workspaceSection ?? 'presupuesto') as PresupuestoSectionId}
              onSectionChange={(s) => setWorkspaceSection(s)}
              flowMsg={flowMsg}
            />
          ) : null}

          {tab === 'pliego' ? (
            <WorkspaceEspecificacionesTab
              project={project}
              projectUuid={projectUuid}
              projectDisplayName={displayTitle}
              token={token}
              role={role}
              pliegoItemStates={pliegoItemStates}
              setPliegoItemStates={setPliegoItemStates}
              pliegoApprovedSections={pliegoApprovedSections}
              setPliegoApprovedSections={setPliegoApprovedSections}
              constructionLines={constructionLines}
              onConstructionLineChange={handleConstructionLineChange}
              constructionApprovedChapters={constructionApprovedChapters}
              setConstructionApprovedChapters={setConstructionApprovedChapters}
              specSummary={specSummary}
              onSpecSummaryChange={setSpecSummary}
              onGenerateConstruction={generateConstructionPliego}
              generateConstructionBusy={generateConstructionBusy}
              onPersist={saveSpecifications}
              specSaveBusy={specSaveBusy}
              flowMsg={flowMsg}
              onApprovePliego={approvePliego}
              onApproveGaFoSection={approveGaFoSection}
              pliegoApproved={pliegoMeta.approved}
              pliegoReadyForApproval={pliegoReadyForApproval}
              pliegoApproveBlocker={pliegoApproveBlocker}
              pliegoEditable={pliegoEditable}
              pliegoReadOnlyHint={pliegoReadOnlyHint}
              pliegoGeneratedAt={pliegoMeta.generatedAt}
              onExportPliegoPdf={() => void exportPliegoPdf()}
              onExportPliegoXlsx={() => void exportPliegoXlsx()}
              onGoPresupuesto={() => selectTab('presupuesto', 'presupuesto')}
            />
          ) : null}

          {tab === 'eventos' ? <WorkspaceEventosTab token={token} projectUuid={projectUuid} /> : null}
          </WorkspaceTabsLayout>
        </div>
      ) : null}

      {tab === 'hub' && !project ? (
        <p className="text-sm text-muted">Cargando proyecto…</p>
      ) : null}

      <ProjectConfigModal
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        projectUuid={projectUuid}
        token={token}
        role={role}
        project={project}
        projectError={projectError}
        onProjectSaved={(p) => {
          setProject(p)
          void loadAuxLists()
        }}
        adminUsers={adminUsers}
        memberRows={memberRows}
        memberSelection={memberSelection}
        setMemberSelection={setMemberSelection}
        membersBusy={membersBusy}
        setMembersBusy={setMembersBusy}
        membersMsg={membersMsg}
        setMembersMsg={setMembersMsg}
        setMemberRows={setMemberRows}
        onProjectRemoved={() => navigate('/app/projects')}
      />
    </div>
  )
}

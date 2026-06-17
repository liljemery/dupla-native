import { useEffect, useMemo, useState } from 'react'
import {
  ArrowRight,
  Check,
  Circle,
  ClipboardCheck,
  LayoutDashboard,
  MessageCircle,
  MoreVertical,
  AlertTriangle,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { hasElevatedAccess } from '../../lib/accessPermissions'
import { useAuthStore } from '../../store/authStore'
import { apiFetch } from '../../api/client'
import { getProjectFilesCount } from '../../api/structuralAnalysis'
import { WORKFLOW_PHASE_ORDER } from '../../constants/workflowPhases'
import { phaseWorkspaceHintForRole } from '../../constants/projectWorkspaceHints'
import type { DirectoryUserRow } from '../../lib/directoryUsers'
import { formatPersonFullName } from '../../lib/personDisplay'
import { userDisplayInitials } from '../../lib/taskboard'
import { workflowPhaseLabelForRole, workflowStepTitleForRole } from '../../lib/accessPermissions'
import { workflowPhaseProgressPct } from '../../lib/projectDashboardBuckets'
import { bootstrapRequiredPercent, isBootstrapComplete } from '../../lib/bootstrapCriteria'
import type { TechnicalFindingRow } from '../../types/projectWorkspace'
import type { BootstrapCriterion, Project } from '../../types/project'
import type { TaskBoardDto } from '../../types/taskBoard'
import { PrimaryButton } from '../PrimaryButton'
import { WorkspaceActionButton } from './WorkspaceActionButton'
import { Card } from '../Card'
import type { TemplateStepProgress } from './WorkflowPhaseStepper'

type ProjectEventRow = {
  uuid: string
  event_type: string
  payload: Record<string, unknown>
  created_at: string
}

type UserNotificationRow = {
  uuid: string
  project_uuid: string | null
  title: string
  body: string | null
  read_at: string | null
  created_at: string
}

type ProjectWorkspaceDashboardProps = {
  project: Project
  projectUuid: string
  token: string | null
  phaseLabel: string
  bpDraft: Record<string, unknown>
  templateStepProgress: TemplateStepProgress | null
  orderedTemplateSteps: { uuid: string; title: string }[] | null
  flowMsg: string | null
  nextPhase: string | undefined
  role: string | null
  viewBudget: boolean
  memberRows: DirectoryUserRow[]
  quotesCount: number
  onAdvancePhase: () => boolean | void | Promise<boolean | void>
  onOpenChat: () => void
  onOpenTab: (tab: string) => void
  onOpenBootstrapChecklist: () => void
  bootstrapCriteria: BootstrapCriterion[]
  pliegoApproved: boolean
  pliegoReadyForApproval: boolean
  canApprovePliego: boolean
  onApprovePliego: () => boolean | void | Promise<boolean | void>
}

function formatBudgetPipelineSummary(bp: Record<string, unknown>): string {
  const keys = [
    'subcontracts_done',
    'volumetry_done',
    'cost_analysis_done',
    'budget_marked_complete',
    'control_review_done',
  ] as const
  let done = 0
  for (const k of keys) {
    if (bp[k] === true) done += 1
  }
  return `${done}/${keys.length}`
}

function daysUntilDeadline(deadline: string | null | undefined): number | null {
  if (!deadline?.trim()) return null
  const d = new Date(`${deadline.trim()}T12:00:00`)
  if (Number.isNaN(d.getTime())) return null
  const now = new Date()
  const diff = d.getTime() - now.getTime()
  return Math.ceil(diff / (24 * 60 * 60 * 1000))
}

export function ProjectWorkspaceDashboard({
  project,
  projectUuid,
  token,
  phaseLabel,
  bpDraft,
  templateStepProgress,
  orderedTemplateSteps,
  flowMsg,
  nextPhase,
  role,
  viewBudget,
  memberRows,
  quotesCount,
  onAdvancePhase,
  onOpenChat,
  onOpenTab,
  onOpenBootstrapChecklist,
  bootstrapCriteria,
  pliegoApproved,
  pliegoReadyForApproval,
  canApprovePliego,
  onApprovePliego,
}: ProjectWorkspaceDashboardProps) {
  const isTeamLeader = useAuthStore((s) => s.isTeamLeader)
  const elevated = hasElevatedAccess(role as import('../../constants/userRoles').UserRole | null, isTeamLeader)
  const [fileTotal, setFileTotal] = useState<number | null>(null)
  const [taskCount, setTaskCount] = useState<number | null>(null)
  const [recentEvents, setRecentEvents] = useState<ProjectEventRow[]>([])
  const [projectNotifs, setProjectNotifs] = useState<UserNotificationRow[]>([])
  const [findings, setFindings] = useState<TechnicalFindingRow[]>([])
  const [teamMenu, setTeamMenu] = useState<string | null>(null)

  const hint = phaseWorkspaceHintForRole(project.workflow_phase, role as import('../../constants/userRoles').UserRole | null)
  const bootstrapStats = useMemo(() => bootstrapRequiredPercent(bootstrapCriteria), [bootstrapCriteria])
  const bootstrapIncomplete = !isBootstrapComplete(bootstrapCriteria)
  const showBootstrapBanner =
    project.workflow_phase === 'BOOTSTRAPPING' || (bootstrapStats.required > 0 && bootstrapIncomplete)
  const showPliegoApproveCta =
    project.workflow_phase === 'SPECIFICATIONS' &&
    canApprovePliego &&
    !pliegoApproved &&
    pliegoReadyForApproval
  const showPliegoPrepareCta =
    project.workflow_phase === 'SPECIFICATIONS' &&
    canApprovePliego &&
    !pliegoApproved &&
    !pliegoReadyForApproval

  const avancePct = useMemo(() => {
    if (templateStepProgress && templateStepProgress.total > 0) {
      const p = ((templateStepProgress.current - 0.5) / templateStepProgress.total) * 100
      return Math.min(100, Math.max(0, Math.round(p * 10) / 10))
    }
    return workflowPhaseProgressPct(project.workflow_phase)
  }, [project.workflow_phase, templateStepProgress])

  const remainingDays = daysUntilDeadline(project.deadline)
  const criticalFindings = useMemo(
    () => findings.filter((f) => f.severity === 'crítico' || f.severity === 'alto'),
    [findings],
  )

  useEffect(() => {
    if (!token || !projectUuid) return
    let cancelled = false
    void (async () => {
      const [fr, ft, fe, fn, ff] = await Promise.all([
        getProjectFilesCount(projectUuid, token),
        apiFetch(`/api/tasks/board?mine=true&project_uuid=${encodeURIComponent(projectUuid)}`, { token }),
        apiFetch(`/api/projects/${projectUuid}/events?limit=5&offset=0`, { token }),
        apiFetch('/api/me/notifications?unread_only=false', { token }),
        apiFetch(`/api/projects/${projectUuid}/technical-findings`, { token }),
      ])
      if (cancelled) return
      if (typeof fr === 'number') setFileTotal(fr)
      if (ft.ok) {
        const board = (await ft.json()) as TaskBoardDto
        let n = board.archived_cards?.length ?? 0
        for (const list of board.lists ?? []) {
          n += list.cards?.length ?? 0
        }
        setTaskCount(n)
      }
      if (fe.ok) {
        const j = (await fe.json()) as { items?: ProjectEventRow[] }
        setRecentEvents(Array.isArray(j.items) ? j.items : [])
      }
      if (fn.ok) {
        const rows = (await fn.json()) as UserNotificationRow[]
        const pid = project.uuid
        setProjectNotifs(rows.filter((r) => r.project_uuid === pid).slice(0, 8))
      }
      if (ff.ok) {
        setFindings((await ff.json()) as TechnicalFindingRow[])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token, projectUuid, project.uuid])

  useEffect(() => {
    if (!teamMenu) return
    const close = () => setTeamMenu(null)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [teamMenu])

  const phaseSteps = useMemo(() => {
    if (orderedTemplateSteps?.length && project.current_workflow_step_uuid) {
      return orderedTemplateSteps.map((s) => ({
        key: s.uuid,
        label: workflowStepTitleForRole(s.title, role as import('../../constants/userRoles').UserRole | null),
      }))
    }
    return WORKFLOW_PHASE_ORDER.map((key) => ({
      key,
      label: workflowPhaseLabelForRole(key, role as import('../../constants/userRoles').UserRole | null),
    }))
  }, [orderedTemplateSteps, project.current_workflow_step_uuid, role])

  const activeStepIdx = useMemo(() => {
    if (orderedTemplateSteps?.length && project.current_workflow_step_uuid) {
      const i = orderedTemplateSteps.findIndex((s) => s.uuid === project.current_workflow_step_uuid)
      return i >= 0 ? i : 0
    }
    const i = WORKFLOW_PHASE_ORDER.indexOf(
      project.workflow_phase as (typeof WORKFLOW_PHASE_ORDER)[number],
    )
    if (project.workflow_phase === 'FILES_INGESTED') {
      const j = WORKFLOW_PHASE_ORDER.indexOf('AWAITING_FILES')
      return j >= 0 ? j : 0
    }
    return i >= 0 ? i : 0
  }, [orderedTemplateSteps, project])

  const currentStepPct =
    phaseSteps.length > 0 ? Math.round(((activeStepIdx + 1) / phaseSteps.length) * 100) : 0

  const unreadProjectNotifs = projectNotifs.filter((n) => !n.read_at).length

  const alertItems = useMemo(() => {
    const out: { key: string; tone: 'critical' | 'warn' | 'info'; title: string; detail?: string }[] =
      []
    for (const n of projectNotifs.filter((x) => !x.read_at).slice(0, 3)) {
      out.push({
        key: `n-${n.uuid}`,
        tone: 'critical',
        title: n.title,
        detail: n.body ?? undefined,
      })
    }
    for (const f of criticalFindings.slice(0, 2)) {
      out.push({
        key: `f-${f.uuid}`,
        tone: 'warn',
        title: f.title,
        detail: f.severity
          ? `${f.severity} · ${(f.description ?? '').slice(0, 120)}`
          : (f.description ?? '').slice(0, 120),
      })
    }
    for (const e of recentEvents.slice(0, 3)) {
      if (out.length >= 6) break
      const title =
        typeof e.payload?.summary === 'string'
          ? (e.payload.summary as string)
          : e.event_type.replace(/_/g, ' ')
      out.push({
        key: `e-${e.uuid}`,
        tone: 'info',
        title,
      })
    }
    return out.slice(0, 6)
  }, [projectNotifs, criticalFindings, recentEvents])

  const quickLinks = (
    <div className="flex flex-wrap gap-2">
      {showBootstrapBanner ? (
        <button
          type="button"
          className="rounded-full border border-primary/35 bg-primary px-3 py-1.5 text-xs font-bold text-white shadow-sm hover:opacity-95"
          onClick={onOpenBootstrapChecklist}
        >
          Checklist de arranque
        </button>
      ) : null}
      <button
        type="button"
        className="rounded-full border border-black/12 bg-white px-3 py-1.5 text-xs font-semibold text-ink shadow-sm hover:border-primary/25"
        onClick={() => onOpenTab('detalles')}
      >
        Detalles
      </button>
      <button
        type="button"
        className="rounded-full border border-black/12 bg-white px-3 py-1.5 text-xs font-semibold text-ink shadow-sm hover:border-primary/25"
        onClick={() => onOpenTab('archivos')}
      >
        Archivos
      </button>
      {viewBudget ? (
        <button
          type="button"
          className="rounded-full border border-black/12 bg-white px-3 py-1.5 text-xs font-semibold text-ink shadow-sm hover:border-primary/25"
          onClick={() => onOpenTab('basePrecios')}
        >
          Base de precios
        </button>
      ) : null}
      <button
        type="button"
        className="rounded-full border border-black/12 bg-white px-3 py-1.5 text-xs font-semibold text-ink shadow-sm hover:border-primary/25"
        onClick={() => onOpenTab('flujo')}
      >
        Flujo
      </button>
      <button
        type="button"
        className="rounded-full border border-black/12 bg-white px-3 py-1.5 text-xs font-semibold text-ink shadow-sm hover:border-primary/25"
        onClick={() => onOpenTab('revisiones')}
      >
        Revisiones
      </button>
      <button
        type="button"
        className="rounded-full border border-black/12 bg-white px-3 py-1.5 text-xs font-semibold text-ink shadow-sm hover:border-primary/25"
        onClick={() => onOpenTab('entregaPlanos')}
      >
        Control de entregas
      </button>
      {viewBudget ? (
        <button
          type="button"
          className="rounded-full border border-primary/25 bg-primary/6 px-3 py-1.5 text-xs font-semibold text-primary shadow-sm hover:border-primary/40"
          onClick={() => onOpenTab('presupuestoMaestro')}
        >
          Presupuesto maestro
        </button>
      ) : null}
      <button
        type="button"
        className="rounded-full border border-black/12 bg-white px-3 py-1.5 text-xs font-semibold text-ink shadow-sm hover:border-primary/25"
        onClick={() => onOpenTab('hallazgos')}
      >
        Hallazgos
      </button>
      <Link
        className="rounded-full border border-black/12 bg-white px-3 py-1.5 text-xs font-semibold text-ink no-underline shadow-sm hover:border-primary/25"
        to={`/app/tasks?mine=true&project_uuid=${encodeURIComponent(projectUuid)}`}
      >
        Tareas
      </Link>
      <button
        type="button"
        className="rounded-full border border-black/12 bg-white px-3 py-1.5 text-xs font-semibold text-ink shadow-sm hover:border-primary/25"
        onClick={onOpenChat}
      >
        Chat
      </button>
    </div>
  )

  const kpiClass =
    'rounded-xl border border-black/10 bg-white px-3 py-3 shadow-(--shadow-card) sm:px-4'

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="flex flex-col gap-5 pb-4">
      {showBootstrapBanner ? (
        <Card className="border-primary/30 bg-primary/6 p-4 shadow-(--shadow-card) ring-1 ring-primary/15 sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary text-white">
                <ClipboardCheck className="size-5" aria-hidden />
              </span>
              <div className="min-w-0">
                <h3 className="text-sm font-bold text-ink">Checklist de arranque pendiente</h3>
                <p className="mt-1 text-sm text-muted">
                  {bootstrapStats.pct != null
                    ? `${bootstrapStats.label}. Guarda el checklist antes de avanzar a «Esperando archivos».`
                    : 'Completa y guarda el checklist de documentos requeridos.'}
                </p>
              </div>
            </div>
            <PrimaryButton
              type="button"
              className="shrink-0 gap-2 px-4 py-2.5 text-sm font-semibold normal-case tracking-normal"
              onClick={onOpenBootstrapChecklist}
            >
              Abrir checklist
              <ArrowRight className="size-4" aria-hidden />
            </PrimaryButton>
          </div>
        </Card>
      ) : null}
      <div className="flex flex-col gap-3">
        {quickLinks}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8">
          <div className={kpiClass}>
            <p className="text-[10px] font-bold uppercase tracking-wide text-muted">Avance %</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-primary">{avancePct}%</p>
          </div>
          {viewBudget ? (
            <div className={kpiClass}>
              <p className="text-[10px] font-bold uppercase tracking-wide text-muted">Presupuesto</p>
              <p className="mt-1 text-lg font-semibold tabular-nums text-ink">{formatBudgetPipelineSummary(bpDraft)}</p>
              <p className="text-[10px] text-muted">Hitos</p>
            </div>
          ) : null}
          {viewBudget ? (
            <div className={kpiClass}>
              <p className="text-[10px] font-bold uppercase tracking-wide text-muted">Cotizaciones</p>
              <p className="mt-1 text-lg font-semibold tabular-nums text-ink">{quotesCount}</p>
            </div>
          ) : null}
          <div className={kpiClass}>
            <p className="text-[10px] font-bold uppercase tracking-wide text-muted">Plazo</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-ink">
              {remainingDays === null ? '—' : `${remainingDays} d`}
            </p>
          </div>
          <div className={kpiClass}>
            <p className="text-[10px] font-bold uppercase tracking-wide text-muted">Documentos</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-ink">
              {fileTotal === null ? '…' : fileTotal}
            </p>
          </div>
          <div className={kpiClass}>
            <p className="text-[10px] font-bold uppercase tracking-wide text-muted">Hallazgos</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-primary">{criticalFindings.length}</p>
          </div>
          <div className={kpiClass}>
            <p className="text-[10px] font-bold uppercase tracking-wide text-muted">Tareas</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-ink">
              {taskCount === null ? '…' : taskCount}
            </p>
          </div>
          <div className={kpiClass}>
            <p className="text-[10px] font-bold uppercase tracking-wide text-muted">Alertas</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-primary">{unreadProjectNotifs}</p>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-5 lg:grid-cols-5">
        <Card className="border-black/10 p-5 shadow-(--shadow-card) lg:col-span-3">
          <h3 data-tour="workspace-tab-nav" className="text-sm font-semibold uppercase tracking-wide text-muted">
            Fases del proyecto
          </h3>
          <ul className="mt-4 space-y-0">
            {phaseSteps.map((s, i) => {
              const done = i < activeStepIdx
              const active = i === activeStepIdx
              return (
                <li key={s.key} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <span
                      className={`flex size-8 shrink-0 items-center justify-center rounded-full border-2 ${
                        done
                          ? 'border-emerald-600 bg-emerald-600 text-white'
                          : active
                            ? 'border-primary bg-primary text-white'
                            : 'border-black/15 bg-white text-muted'
                      }`}
                    >
                      {done ? (
                        <Check className="size-4" strokeWidth={2.5} aria-hidden />
                      ) : active ? (
                        <span className="text-[11px] font-bold tabular-nums">{i + 1}</span>
                      ) : (
                        <Circle className="size-4" strokeWidth={2} aria-hidden />
                      )}
                    </span>
                    {i < phaseSteps.length - 1 ? (
                      <span className="my-1 w-px flex-1 min-h-5 bg-black/10" aria-hidden />
                    ) : null}
                  </div>
                  <div className={`min-w-0 flex-1 pb-6 ${active ? '-mt-0.5' : ''}`}>
                    <p className={`text-sm font-semibold leading-snug ${active ? 'text-primary' : 'text-ink'}`}>
                      {s.label}
                    </p>
                    {active ? (
                      <div className="mt-2 rounded-lg border border-primary/20 bg-primary/6 p-3">
                        <p className="text-xs font-medium text-ink">
                          Fase actual · {currentStepPct}% completado
                        </p>
                        <div className="mt-2 h-2 overflow-hidden rounded-full bg-black/10">
                          <div
                            className="h-full rounded-full bg-primary transition-[width]"
                            style={{ width: `${currentStepPct}%` }}
                          />
                        </div>
                        {hint ? (
                          <div className="mt-3 border-t border-black/5 pt-2.5">
                            <p className="text-xs font-semibold text-ink">{hint.title}</p>
                            <p className="mt-1 text-xs leading-relaxed text-muted">{hint.body}</p>
                            <button
                              type="button"
                              className="mt-2.5 inline-flex items-center gap-1.5 text-xs font-bold text-primary hover:underline"
                              onClick={() => {
                                const targetTab =
                                  hint.tabId === 'documentos'
                                    ? 'archivos'
                                    : hint.tabId === 'resumen' || hint.tabId === 'hub'
                                      ? 'hub'
                                      : hint.tabId === 'historial'
                                        ? 'eventos'
                                        : hint.tabId === 'flujo' && project.workflow_phase === 'BOOTSTRAPPING'
                                          ? 'flujo-bootstrap'
                                          : hint.tabId
                                if (targetTab === 'flujo-bootstrap') {
                                  onOpenBootstrapChecklist()
                                } else {
                                  onOpenTab(targetTab)
                                }
                              }}
                            >
                              {hint.cta}
                              <ArrowRight className="size-3" aria-hidden />
                            </button>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </li>
              )
            })}
          </ul>
          <div className="mt-4 flex flex-wrap gap-2 border-t border-black/8 pt-4">
            <button
              type="button"
              className="du-pill-action inline-flex items-center gap-2 text-sm font-semibold"
              onClick={() => onOpenTab('flujo')}
            >
              <LayoutDashboard className="size-4" aria-hidden />
              Abrir flujo
            </button>
            <button
              type="button"
              className="du-pill-action inline-flex items-center gap-2 text-sm font-semibold"
              onClick={onOpenChat}
            >
              <MessageCircle className="size-4" aria-hidden />
              Chat del proyecto
            </button>
          </div>
          {flowMsg ? <p className="mt-3 text-sm text-primary">{flowMsg}</p> : null}
        </Card>

        <div className="flex flex-col gap-4 lg:col-span-2">
          <Card className="border-black/10 p-5 shadow-(--shadow-card)">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">Alertas</h3>
              {unreadProjectNotifs > 0 ? (
                <span className="rounded-full bg-primary/12 px-2 py-0.5 text-[10px] font-bold text-primary">
                  {unreadProjectNotifs} nuevas
                </span>
              ) : null}
            </div>
            <ul className="mt-3 space-y-2">
              {alertItems.length === 0 ? (
                <li className="rounded-lg border border-black/8 bg-black/2 px-3 py-6 text-center text-sm text-muted">
                  Sin alertas recientes.
                </li>
              ) : (
                alertItems.map((a) => (
                  <li
                    key={a.key}
                    className={`rounded-lg border px-3 py-2.5 text-sm ${
                      a.tone === 'critical'
                        ? 'border-primary/25 bg-primary/6 text-ink'
                        : a.tone === 'warn'
                          ? 'border-amber-200 bg-amber-50 text-ink'
                          : 'border-black/10 bg-white'
                    }`}
                  >
                    <div className="flex gap-2">
                      <AlertTriangle
                        className={`mt-0.5 size-4 shrink-0 ${a.tone === 'critical' ? 'text-primary' : 'text-amber-600'}`}
                        aria-hidden
                      />
                      <div className="min-w-0">
                        <p className="font-semibold leading-snug">{a.title}</p>
                        {a.detail ? <p className="mt-1 text-xs leading-relaxed text-muted">{a.detail}</p> : null}
                      </div>
                    </div>
                  </li>
                ))
              )}
            </ul>
          </Card>

          <Card className="border-black/10 p-5 shadow-(--shadow-card)">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">Equipo del proyecto</h3>
            <ul className="mt-3 divide-y divide-black/8">
              {memberRows.length === 0 ? (
                <li className="py-4 text-sm text-muted">No hay otros miembros listados.</li>
              ) : (
                memberRows.slice(0, 8).map((m) => {
                  const name = formatPersonFullName(m.first_name, m.last_name, m.email)
                  const subtitle = m.role?.trim() ? m.role : m.email
                  const initials = userDisplayInitials(m.first_name, m.last_name, m.email)
                  return (
                    <li key={m.uuid} className="relative flex items-center gap-3 py-3">
                      <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary/12 text-xs font-bold text-primary">
                        {initials}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium text-ink">{name}</p>
                        <p className="truncate text-xs text-muted">{subtitle}</p>
                      </div>
                      <div className="relative shrink-0">
                        <button
                          type="button"
                          className="rounded-md p-1.5 text-muted hover:bg-black/5"
                          aria-label={`Opciones · ${name}`}
                          aria-expanded={teamMenu === m.uuid}
                          onClick={(e) => {
                            e.stopPropagation()
                            setTeamMenu((id) => (id === m.uuid ? null : m.uuid))
                          }}
                        >
                          <MoreVertical className="size-4" aria-hidden />
                        </button>
                        {teamMenu === m.uuid ? (
                          <div className="absolute right-0 top-full z-10 mt-1 w-36 rounded-lg border border-black/10 bg-white py-1 shadow-lg">
                            <button
                              type="button"
                              className="block w-full px-3 py-2 text-left text-xs text-ink hover:bg-black/4"
                              onClick={() => {
                                setTeamMenu(null)
                                onOpenTab('detalles')
                              }}
                            >
                              Ver detalles
                            </button>
                          </div>
                        ) : null}
                      </div>
                    </li>
                  )
                })
              )}
            </ul>
          </Card>
        </div>
      </div>
        </div>
      </div>

      <div className="shrink-0 flex flex-col gap-3 border-t border-black/10 bg-surface py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <span className="text-[10px] font-bold uppercase tracking-wide text-muted">Fase actual</span>
          <span className="truncate font-semibold text-ink">{phaseLabel}</span>
        </div>
        {flowMsg ? <p className="w-full text-sm text-primary">{flowMsg}</p> : null}
        {showPliegoPrepareCta ? (
          <div className="flex w-full flex-wrap items-center gap-2 rounded-lg border border-black/15 bg-black/4 px-3 py-2.5">
            <p className="min-w-0 flex-1 text-xs text-ink">
              Genera o completa el pliego en la pestaña Pliego antes de solicitar la aprobación de Arquitectura.
            </p>
            <button
              type="button"
              className="rounded-lg border border-black/15 bg-white px-3 py-2 text-xs font-semibold text-ink shadow-sm hover:bg-black/3"
              onClick={() => onOpenTab('pliego')}
            >
              Ir al pliego
            </button>
          </div>
        ) : null}
        {showPliegoApproveCta ? (
          <div className="flex w-full flex-wrap items-center gap-2 rounded-lg border border-primary/25 bg-primary/6 px-3 py-2.5">
            <p className="min-w-0 flex-1 text-xs text-ink">
              El pliego está pendiente de aprobación de Arquitectura antes de avanzar al presupuesto.
            </p>
            <button
              type="button"
              className="rounded-lg border border-black/15 bg-white px-3 py-2 text-xs font-semibold text-ink shadow-sm hover:bg-black/3"
              onClick={() => onOpenTab('pliego')}
            >
              Ir al pliego
            </button>
            <WorkspaceActionButton
              type="button"
              className="px-3 py-2 text-xs font-semibold normal-case tracking-normal"
              onAction={onApprovePliego}
              successLabel="Pliego aprobado"
              runningLabel="Aprobando…"
            >
              Aprobar pliego
            </WorkspaceActionButton>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-lg border border-black/15 bg-white px-4 py-2.5 text-sm font-semibold text-ink shadow-sm hover:bg-black/3"
            onClick={() => onOpenTab('detalles')}
          >
            Ver detalles
          </button>
          {nextPhase ? (
            <WorkspaceActionButton
              type="button"
              className="gap-2 px-4 py-2.5 text-sm font-semibold normal-case tracking-normal"
              onAction={onAdvancePhase}
              successLabel="Fase actualizada"
              runningLabel="Procesando…"
            >
              Continuar fase
              <ArrowRight className="size-4" aria-hidden />
            </WorkspaceActionButton>
          ) : (
            <span className="self-center text-xs text-muted">Última fase alcanzada.</span>
          )}
        </div>
        {nextPhase === 'BUDGET_APPROVED' && viewBudget && !elevated ? (
          <p className="w-full text-xs text-primary sm:w-auto">
            Solo Gerencia o Líder de equipo puede cerrar la aprobación final del presupuesto.
          </p>
        ) : null}
      </div>
    </div>
  )
}


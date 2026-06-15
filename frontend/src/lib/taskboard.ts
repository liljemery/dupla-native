import { WORKFLOW_PHASE_LABELS } from '../constants/workflowPhases'
import type { TaskCardDto } from '../types/taskBoard'

export const CARD_MIME = 'application/x-dupla-task-card'

const AVATAR_RING = [
  'bg-emerald-600',
  'bg-sky-600',
  'bg-amber-600',
  'bg-violet-600',
  'bg-rose-600',
  'bg-cyan-600',
  'bg-fuchsia-600',
  'bg-lime-700',
]

export function labelForCreatedPhase(phase: string | null | undefined): string | null {
  if (!phase) return null
  return WORKFLOW_PHASE_LABELS[phase] ?? phase
}

export function emailInitials(email: string): string {
  const local = email.split('@')[0] ?? email
  const parts = local.split(/[._\-+]+/).filter(Boolean)
  if (parts.length >= 2) {
    return (parts[0]!.charAt(0) + parts[1]!.charAt(0)).toUpperCase().slice(0, 2)
  }
  return local.slice(0, 2).toUpperCase() || '?'
}

/** Inicial del nombre + inicial del apellido; si faltan datos, mismo criterio que antes con el correo. */
export function userDisplayInitials(
  firstName: string | null | undefined,
  lastName: string | null | undefined,
  email: string,
): string {
  const f = (firstName ?? '').trim()
  const l = (lastName ?? '').trim()
  if (f.length > 0 && l.length > 0) {
    return (f.charAt(0) + l.charAt(0)).toUpperCase().slice(0, 2)
  }
  return emailInitials(email)
}

export function hueClassForUuid(uuid: string): string {
  let h = 0
  for (let i = 0; i < uuid.length; i += 1) h = (h + uuid.charCodeAt(i) * (i + 1)) % 997
  return AVATAR_RING[h % AVATAR_RING.length]!
}

export function cardMatchesSearch(card: TaskCardDto, needle: string): boolean {
  if (!needle) return true
  const t = card.title.toLowerCase()
  const d = (card.description ?? '').toLowerCase()
  const a = (card.assignee_email ?? '').toLowerCase()
  const c = (card.creator_email ?? '').toLowerCase()
  const af = (card.assignee_first_name ?? '').toLowerCase()
  const al = (card.assignee_last_name ?? '').toLowerCase()
  const cf = (card.creator_first_name ?? '').toLowerCase()
  const cl = (card.creator_last_name ?? '').toLowerCase()
  const ph = labelForCreatedPhase(card.created_in_phase)?.toLowerCase() ?? ''
  const pn = (card.project_name ?? '').toLowerCase()
  const pc = (card.project_code ?? '').toLowerCase()
  return (
    t.includes(needle) ||
    d.includes(needle) ||
    a.includes(needle) ||
    c.includes(needle) ||
    af.includes(needle) ||
    al.includes(needle) ||
    cf.includes(needle) ||
    cl.includes(needle) ||
    ph.includes(needle) ||
    pn.includes(needle) ||
    pc.includes(needle)
  )
}

export function boardQueryParams(includeArchived: boolean, projectUuid: string): string {
  const p = new URLSearchParams()
  p.set('mine', 'true')
  if (includeArchived) p.set('include_archived', 'true')
  if (projectUuid) p.set('project_uuid', projectUuid)
  const s = p.toString()
  return s ? `?${s}` : ''
}

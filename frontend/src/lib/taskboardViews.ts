import type { TaskCardDto, TaskListDto } from '../types/taskBoard'

export type TaskViewMode = 'board' | 'list'

export type FlatTaskRow = {
  card: TaskCardDto
  listTitle: string
}

export function flattenBoardLists(lists: TaskListDto[]): FlatTaskRow[] {
  const out: FlatTaskRow[] = []
  for (const list of lists) {
    for (const card of list.cards) {
      out.push({ card, listTitle: list.title })
    }
  }
  return out
}

export type TaskboardKpis = {
  assigned: number
  inProgress: number
  atRisk: number
  completed: number
  compliancePct: number
}

function normTitle(t: string): string {
  return t.trim().toLowerCase()
}

/** KPIs derivados de los títulos de lista estándar (Por hacer, Bloqueado, En progreso, En revisión, Hecho). */
export function computeTaskboardKpis(lists: TaskListDto[]): TaskboardKpis {
  let assigned = 0
  let inProgress = 0
  let atRisk = 0
  let completed = 0
  for (const list of lists) {
    const t = normTitle(list.title)
    const n = list.cards.length
    assigned += n
    if (t.includes('hecho')) completed += n
    else if (t.includes('bloqueado')) atRisk += n
    else if (t.includes('progreso') || t.includes('revisión') || t.includes('revision')) inProgress += n
  }
  const denom = assigned > 0 ? assigned : 1
  const compliancePct = Math.min(100, Math.round((completed / denom) * 100))
  return { assigned, inProgress, atRisk, completed, compliancePct }
}

export type ListColumnAccent = 'grey' | 'red' | 'amber' | 'green'

export function columnAccentForListTitle(title: string): ListColumnAccent {
  const t = normTitle(title)
  if (t.includes('hecho')) return 'green'
  if (t.includes('bloqueado')) return 'red'
  if (t.includes('revisión') || t.includes('revision')) return 'amber'
  if (t.includes('progreso')) return 'red'
  return 'grey'
}

export type StatusPresentation = {
  label: string
  pillClass: string
}

export function statusPresentationForListTitle(title: string): StatusPresentation {
  const t = normTitle(title)
  if (t.includes('hecho'))
    return { label: 'Completado', pillClass: 'border-emerald-500/35 bg-emerald-500/12 text-emerald-800' }
  if (t.includes('bloqueado'))
    return { label: 'Bloqueado', pillClass: 'border-primary/40 bg-primary/12 text-primary' }
  if (t.includes('revisión') || t.includes('revision'))
    return { label: 'En revisión', pillClass: 'border-amber-500/40 bg-amber-500/12 text-amber-900' }
  if (t.includes('progreso'))
    return { label: 'En proceso', pillClass: 'border-amber-500/35 bg-amber-400/15 text-amber-950' }
  return { label: 'Pendiente', pillClass: 'border-black/15 bg-black/[0.04] text-ink' }
}

export function priorityLabelForListTitle(title: string): { label: string; dotClass: string } {
  const t = normTitle(title)
  if (t.includes('bloqueado')) return { label: 'Crítica', dotClass: 'bg-primary' }
  if (t.includes('revisión') || t.includes('revision') || t.includes('progreso'))
    return { label: 'Alta', dotClass: 'bg-amber-500' }
  if (t.includes('hecho')) return { label: '—', dotClass: 'bg-emerald-500' }
  return { label: 'Media', dotClass: 'bg-black/25' }
}

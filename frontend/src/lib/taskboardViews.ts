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

function listBucket(title: string): 'todo' | 'progress' | 'done' {
  const t = normTitle(title)
  if (t.includes('completado') || t.includes('hecho')) return 'done'
  if (t.includes('progreso')) return 'progress'
  return 'todo'
}

/** KPIs derivados de las columnas del tablero (API). */
export function computeTaskboardKpis(lists: TaskListDto[]): TaskboardKpis {
  let assigned = 0
  let inProgress = 0
  let completed = 0
  for (const list of lists) {
    const n = list.cards.length
    assigned += n
    const bucket = listBucket(list.title)
    if (bucket === 'done') completed += n
    else if (bucket === 'progress') inProgress += n
  }
  const denom = assigned > 0 ? assigned : 1
  const compliancePct = Math.min(100, Math.round((completed / denom) * 100))
  return { assigned, inProgress, atRisk: 0, completed, compliancePct }
}

export type ListColumnAccent = 'grey' | 'amber' | 'green'

export function columnAccentForListTitle(title: string): ListColumnAccent {
  const bucket = listBucket(title)
  if (bucket === 'done') return 'green'
  if (bucket === 'progress') return 'amber'
  return 'grey'
}

export type StatusPresentation = {
  label: string
  pillClass: string
}

export function statusPresentationForListTitle(title: string): StatusPresentation {
  const bucket = listBucket(title)
  if (bucket === 'done')
    return { label: 'Completado', pillClass: 'border-emerald-500/35 bg-emerald-500/12 text-emerald-800' }
  if (bucket === 'progress')
    return { label: 'En progreso', pillClass: 'border-amber-500/35 bg-amber-400/15 text-amber-950' }
  return { label: 'Por hacer', pillClass: 'border-black/15 bg-black/[0.04] text-ink' }
}

export function priorityLabelForListTitle(title: string): { label: string; dotClass: string } {
  const bucket = listBucket(title)
  if (bucket === 'done') return { label: '—', dotClass: 'bg-emerald-500' }
  if (bucket === 'progress') return { label: 'Alta', dotClass: 'bg-amber-500' }
  return { label: 'Media', dotClass: 'bg-black/25' }
}

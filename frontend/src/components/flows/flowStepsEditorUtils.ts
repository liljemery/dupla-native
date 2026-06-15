import {
  DEFAULT_FLOW_TEMPLATE_ICON,
  type FlowTemplateIconKey,
} from '../../constants/flowTemplateIcons'
import { generateUuid } from '../../lib/uuid'

export type EnterActionType = 'notify_role' | 'create_task' | 'project_chat_message'

export type DraftWorkflowStep = {
  draft_id: string
  server_step_uuid?: string | null
  stable_key: string
  title: string
  icon_key: FlowTemplateIconKey
  requires_approval_role: string | null
  on_enter_actions: Record<string, unknown>[]
}

const STABLE_KEY_MAX = 128

export function newDraftId(): string {
  return generateUuid()
}

export function stableKeyFromTitle(title: string, index: number): string {
  const t = title.trim()
  if (!t) return `paso_${index + 1}`
  return t.replace(/\s+/g, '_').toLowerCase().slice(0, STABLE_KEY_MAX)
}

export function syncStableKeysForSteps(steps: DraftWorkflowStep[]): DraftWorkflowStep[] {
  const used = new Set<string>()
  return steps.map((s, i) => {
    const base = stableKeyFromTitle(s.title, i)
    let candidate = base
    let n = 2
    while (used.has(candidate)) {
      candidate = `${base}_${n}`
      n += 1
    }
    used.add(candidate)
    return { ...s, stable_key: candidate }
  })
}

export function normalizeActionsFromApi(raw: unknown): Record<string, unknown>[] {
  if (!Array.isArray(raw)) return []
  const out: Record<string, unknown>[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const o = item as Record<string, unknown>
    const t = String(o.type ?? '')
    if (t === 'notify_role') {
      out.push({
        type: 'notify_role',
        role: String(o.role ?? 'CONTROL'),
        title: String(o.title ?? ''),
        body: String(o.body ?? ''),
      })
    } else if (t === 'create_task') {
      out.push({
        type: 'create_task',
        role: String(o.role ?? 'CONTROL'),
        title: String(o.title ?? ''),
        description: String(o.description ?? ''),
      })
    } else if (t === 'project_chat_message') {
      out.push({
        type: 'project_chat_message',
        body: String(o.body ?? ''),
      })
    }
  }
  return out
}

export function emptyDraftStep(): DraftWorkflowStep {
  return {
    draft_id: newDraftId(),
    stable_key: 'paso_1',
    title: '',
    icon_key: DEFAULT_FLOW_TEMPLATE_ICON,
    requires_approval_role: null,
    on_enter_actions: [],
  }
}

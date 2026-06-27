import type { RevisionRow } from '../types/projectWorkspace'

export function managementApprovalEnteredAt(
  meta: Record<string, unknown> | null | undefined,
): number | null {
  const raw = meta?.management_approval_entered_at
  if (typeof raw !== 'string' || !raw.trim()) return null
  const t = Date.parse(raw)
  return Number.isFinite(t) ? t : null
}

export function hasGerenciaRevisionSinceManagementPhase(
  revisions: RevisionRow[],
  meta: Record<string, unknown> | null | undefined,
  workflowPhase: string,
): boolean {
  let since = managementApprovalEnteredAt(meta)
  // ponytail: legacy projects in gerencia phase before timestamp existed
  if (since == null && workflowPhase === 'MANAGEMENT_APPROVAL') {
    since = 0
  }
  if (since == null) return false
  return revisions.some(
    (r) => r.revision_role === 'GERENCIA' && Date.parse(r.created_at) >= since,
  )
}

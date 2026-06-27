const BUDGET_PIPELINE_PHASES = new Set([
  'BUDGETING_PIPELINE',
  'MANAGEMENT_APPROVAL',
  'BUDGET_APPROVED',
  'COMPLETE',
])

export function showBudgetPipelinePanel(phase: string | undefined): boolean {
  return !!phase && BUDGET_PIPELINE_PHASES.has(phase)
}

const PHASES_AFTER_BUDGET = ['MANAGEMENT_APPROVAL', 'BUDGET_APPROVED', 'COMPLETE'] as const

export const BUDGET_EXCLUDED_UPLOAD_NOTICE =
  'Los archivos subidos después de la fase de presupuesto no se incluirán en el presupuesto.'

export function uploadsExcludedFromBudget(workflowPhase: string): boolean {
  return (PHASES_AFTER_BUDGET as readonly string[]).includes(workflowPhase)
}

export const BUDGET_EXCLUDED_FILE_BADGE = 'Fuera de presupuesto'

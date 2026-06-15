export function budgetPipeline(meta: Record<string, unknown>): Record<string, unknown> {
  const bp = meta.budget_pipeline
  return typeof bp === 'object' && bp !== null ? { ...(bp as Record<string, unknown>) } : {}
}

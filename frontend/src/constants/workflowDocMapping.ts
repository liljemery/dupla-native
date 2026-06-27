/** Pistas por fase (resumen corto en UI). */
export const WORKFLOW_DOC_PHASE_HINTS: Record<string, string> = {
  AWAITING_FILES: 'Doc: documentación cargada; pendiente completar archivos CAD/PDF.',
  FILES_INGESTED: 'Doc (legado): archivos ingresados; equivale a «esperando archivos» en flujo nuevo.',
  ARCHITECTURE_REVIEW: 'Doc: en revisión de arquitectura.',
  SPECIFICATIONS: 'Doc: pliego de condiciones / especificaciones.',
  BUDGETING_PIPELINE: 'Doc: presupuesto — cotizaciones, volumetría, costo e hitos del pipeline.',
  MANAGEMENT_APPROVAL: 'Doc: revisión Control / gerencia antes del cierre económico.',
  BUDGET_APPROVED: 'Doc: versión aprobada por el cliente.',
  COMPLETE: 'Doc: obra cerrada en flujo.',
}

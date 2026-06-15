/** Estado de una corrida de análisis (API futura). */
export type StructuralAnalysisRunStatus = 'pending' | 'running' | 'completed' | 'failed'

/** Severidad visual del choque / hallazgo automático. */
export type StructuralClashPriority = 'critical' | 'high' | 'warning' | 'info'

/** Un choque o inconsistencia detectada entre disciplinas o normativa. */
export type StructuralClash = {
  id: string
  title: string
  description: string
  priority: StructuralClashPriority
  location_label: string | null
  disciplines: string[]
  /** URL de miniatura 3D o captura; opcional hasta que la API lo provea. */
  thumbnail_url: string | null
}

/** Documento considerado en el análisis y su estado de ingestión. */
export type StructuralAnalyzedDocument = {
  id: string
  file_name: string
  discipline_label: string
  status: 'ok' | 'error' | 'pending' | 'warning'
  retryable: boolean
  element_count?: number
}

/** Fila de la tabla de zonificación / cumplimiento por zona. */
export type StructuralZoningRow = {
  id: string
  zone_name: string
  area_sqm: number
  use_type: string
  ai_remarks: string
  status: 'validated' | 'error' | 'warning'
}

/**
 * Relación entre hallazgos (p. ej. contradicción, duplicado).
 * La API puede señalar conflictos lógicos entre ítems del informe.
 */
export type StructuralClashRelationship = {
  id: string
  kind: 'contradicts' | 'duplicate' | 'related'
  clash_ids: string[]
  message: string
}

/** Payload esperado de GET /api/projects/.../structural-analysis-report (nombre tentativo). */
export type StructuralAnalysisReport = {
  run_status: StructuralAnalysisRunStatus
  /** real = motor Dupla; smoke = fixture de desarrollo */
  analysis_mode?: 'real' | 'smoke'
  title: string
  subtitle: string
  summary: {
    errors: number
    warnings: number
    ok: number
    total_clashes?: number
    critical?: number
    non_critical?: number
  }
  clashes: StructuralClash[]
  clash_relationships: StructuralClashRelationship[]
  analyzed_documents: StructuralAnalyzedDocument[]
  ai_insight: string
  zoning_rows: StructuralZoningRow[]
  footer_status_message: string
}

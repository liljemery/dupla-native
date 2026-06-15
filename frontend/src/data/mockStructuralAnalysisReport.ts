import type { StructuralAnalysisReport } from '../types/structuralAnalysisReport'

/** Datos de demostración hasta conectar la API de análisis / clashes. */
export const MOCK_STRUCTURAL_ANALYSIS_REPORT: StructuralAnalysisReport = {
  run_status: 'completed',
  title: 'Informe de análisis estructural (IA)',
  subtitle:
    'Revisión automática de cumplimiento de normativa y colisiones entre disciplinas. Los valores son de ejemplo.',
  summary: {
    errors: 12,
    warnings: 8,
    ok: 142,
  },
  clashes: [
    {
      id: 'clash-1',
      title: 'Interferencia: estructura vs. HVAC',
      description: 'Viga V-204 obstruye ducto de extracción principal.',
      priority: 'high',
      location_label: 'Nivel 02, zona norte',
      disciplines: ['Estructura', 'Mecánica'],
      thumbnail_url: null,
    },
    {
      id: 'clash-2',
      title: 'Inconsistencia normativa: recubrimientos',
      description: 'Espesor declarado no coincide con resistencia al fuego exigida para el uso actual.',
      priority: 'critical',
      location_label: 'Nivel 01 — núcleo sanitario',
      disciplines: ['Arquitectura', 'Seguridad'],
      thumbnail_url: null,
    },
    {
      id: 'clash-3',
      title: 'Interferencia: eléctrica vs. sanitaria',
      description: 'Bandejado propuesto cruza vano de bajantes sin distancia mínima reglamentaria.',
      priority: 'warning',
      location_label: 'Planta baja — cocina',
      disciplines: ['Eléctrica', 'Sanitaria'],
      thumbnail_url: null,
    },
  ],
  clash_relationships: [
    {
      id: 'rel-1',
      kind: 'contradicts',
      clash_ids: ['clash-1', 'clash-3'],
      message:
        'Hay solapamiento de criterios de coordinación entre el choque estructura/HVAC y el cruce eléctrico/sanitario en la misma zona del modelo. Conviene revisar el orden de prelación de instalaciones.',
    },
  ],
  analyzed_documents: [
    {
      id: 'doc-1',
      file_name: 'EST-V2-PLANO.dwg',
      discipline_label: 'Estructura',
      status: 'ok',
      retryable: false,
    },
    {
      id: 'doc-2',
      file_name: 'MEP-INSTALACIONES.ifc',
      discipline_label: 'Instalaciones',
      status: 'ok',
      retryable: false,
    },
    {
      id: 'doc-3',
      file_name: 'ARC-FINAL.rvt',
      discipline_label: 'Arquitectura',
      status: 'error',
      retryable: true,
    },
  ],
  ai_insight:
    'Recomendamos priorizar la coordinación entre equipos de estructura e instalaciones mecánicas en el nivel 2: el informe anticipa un posible sobrecosto de obra si no se resuelven las interferencias detectadas antes de licitación.',
  zoning_rows: [
    {
      id: 'z-1',
      zone_name: 'Planta baja — hall',
      area_sqm: 120.5,
      use_type: 'Público',
      ai_remarks: 'Niveles de iluminación adecuados según criterio revisado.',
      status: 'validated',
    },
    {
      id: 'z-2',
      zone_name: 'Nivel 1 — oficinas A',
      area_sqm: 450.0,
      use_type: 'Administrativo',
      ai_remarks: 'La densidad de ocupación supera el margen habitual frente a norma contra incendios.',
      status: 'error',
    },
  ],
  footer_status_message:
    'El análisis de ejemplo está listo. Cuando la API esté conectada, aquí verás el estado real de la corrida y las acciones disponibles.',
}

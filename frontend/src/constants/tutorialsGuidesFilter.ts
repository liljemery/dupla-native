/** Filtros visuales «Tutoriales y Guías» (misma página; solo agrupa contenido). */
export type TutorialsGuidesFilter = 'primeros' | 'proyectos' | 'presupuesto'

export const TUTORIALS_GUIDE_FILTERS: { id: TutorialsGuidesFilter; label: string }[] = [
  { id: 'primeros', label: 'Primeros pasos' },
  { id: 'proyectos', label: 'Proyectos' },
  { id: 'presupuesto', label: 'Presupuesto' },
]

/** IDs de `TUTORIALS_TOC` visibles por filtro en la guía escrita. */
export const TUTORIALS_TOC_IDS_BY_FILTER: Record<TutorialsGuidesFilter, readonly string[]> = {
  primeros: ['navegacion', 'chat', 'avisos', 'admin'],
  proyectos: [
    'proyectos',
    'workspace',
    'detalles',
    'archivos',
    'entrega-planos',
    'revisiones',
    'hallazgos',
    'pliego',
    'eventos',
    'config-proyecto',
  ],
  presupuesto: ['flujo', 'tablero'],
}

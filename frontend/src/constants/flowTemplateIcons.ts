/** Lucide icon component names allowed for workflow templates (must match backend). */
export const FLOW_TEMPLATE_ICON_KEYS = [
  'GitBranch',
  'Workflow',
  'Layers',
  'Boxes',
  'Kanban',
  'LayoutGrid',
  'CircleDot',
  'ArrowRight',
  'GitFork',
  'Route',
  'Map',
  'Building2',
  'HardHat',
  'DraftingCompass',
  'Ruler',
  'Hammer',
  'ClipboardList',
  'CheckCircle',
  'CirclePlay',
  'Timer',
  'Zap',
] as const

export type FlowTemplateIconKey = (typeof FLOW_TEMPLATE_ICON_KEYS)[number]

/** Etiquetas en español para selectores (el valor enviado al API sigue siendo la clave Lucide). */
export const FLOW_TEMPLATE_ICON_LABELS_ES: Record<FlowTemplateIconKey, string> = {
  GitBranch: 'Ramas del flujo',
  Workflow: 'Flujo de trabajo',
  Layers: 'Capas',
  Boxes: 'Módulos',
  Kanban: 'Tablero tipo Kanban',
  LayoutGrid: 'Cuadrícula',
  CircleDot: 'Punto focal',
  ArrowRight: 'Siguiente / avanzar',
  GitFork: 'Bifurcación',
  Route: 'Ruta',
  Map: 'Mapa',
  Building2: 'Edificio',
  HardHat: 'Obra / casco',
  DraftingCompass: 'Compás técnico',
  Ruler: 'Medición',
  Hammer: 'Construcción',
  ClipboardList: 'Lista de control',
  CheckCircle: 'Aprobado / verificado',
  CirclePlay: 'En curso',
  Timer: 'Plazos / tiempo',
  Zap: 'Acción rápida',
}

export function flowTemplateIconLabelEs(key: FlowTemplateIconKey): string {
  return FLOW_TEMPLATE_ICON_LABELS_ES[key]
}

export const DEFAULT_FLOW_TEMPLATE_ICON: FlowTemplateIconKey = 'GitBranch'

export function coerceFlowTemplateIconKey(name: string | undefined): FlowTemplateIconKey {
  const k = name ?? ''
  if ((FLOW_TEMPLATE_ICON_KEYS as readonly string[]).includes(k)) return k as FlowTemplateIconKey
  return DEFAULT_FLOW_TEMPLATE_ICON
}

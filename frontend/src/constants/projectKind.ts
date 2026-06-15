export type ProjectKindValue = 'TENDER' | 'CLIENT' | 'DEVELOPMENT'

export const PROJECT_KIND_OPTIONS: { value: ProjectKindValue; label: string; description: string }[] = [
  {
    value: 'TENDER',
    label: 'Licitación',
    description: 'Inicia en revisión de arquitectura; requiere subir uno o más archivos al crear.',
  },
  {
    value: 'CLIENT',
    label: 'Cliente',
    description: 'Flujo completo desde criterios de arranque (obra directa con cliente).',
  },
  {
    value: 'DEVELOPMENT',
    label: 'Desarrollo',
    description: 'Flujo completo desde criterios de arranque (obra interna / desarrollo).',
  },
]

export function projectKindLabel(kind: string | undefined): string {
  if (kind === 'TENDER') return 'Licitación'
  if (kind === 'CLIENT') return 'Cliente'
  if (kind === 'DEVELOPMENT') return 'Desarrollo'
  if (kind === 'RESIDENTIAL') return 'Cliente'
  return kind ?? '—'
}

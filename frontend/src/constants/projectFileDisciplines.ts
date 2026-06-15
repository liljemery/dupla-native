export const PROJECT_FILE_DISCIPLINE_VALUES = [
  'arquitectura',
  'estructura',
  'mecanica',
  'electrica',
  'plomeria',
] as const

export type ProjectFileDisciplineValue = (typeof PROJECT_FILE_DISCIPLINE_VALUES)[number]

export const PROJECT_FILE_DISCIPLINE_LABELS: Record<ProjectFileDisciplineValue, string> = {
  arquitectura: 'Arquitectura',
  estructura: 'Estructura',
  mecanica: 'Mecánica',
  electrica: 'Eléctrica',
  plomeria: 'Plomería / hidrosanitaria',
}

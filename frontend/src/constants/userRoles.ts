export const USER_ROLES = ['GERENCIA', 'CONTROL', 'PRESUPUESTO', 'ARQUITECTURA'] as const

export type UserRole = (typeof USER_ROLES)[number]

export const ROLE_LABELS: Record<UserRole, string> = {
  GERENCIA: 'Gerencia',
  CONTROL: 'Control',
  PRESUPUESTO: 'Presupuesto',
  ARQUITECTURA: 'Arquitectura',
}

/** Roles de campo (antes operario): Presupuesto y Arquitectura. */
export function isFieldRole(role: string | null): boolean {
  return role === 'PRESUPUESTO' || role === 'ARQUITECTURA'
}

import type { PliegoItemEstado } from '../types/pliegoForm'

export const PLIEGO_ITEM_ESTADO_OPTIONS: { value: PliegoItemEstado; label: string }[] = [
  { value: 'PENDIENTE', label: 'Pendiente' },
  { value: 'COMPLETO', label: 'Completo' },
  { value: 'INCOMPLETO', label: 'Incompleto' },
  { value: 'EN_REVISION', label: 'En revisión' },
  { value: 'NO_APLICA', label: 'No aplica' },
]

export function pliegoEstadoLabel(e: PliegoItemEstado): string {
  return PLIEGO_ITEM_ESTADO_OPTIONS.find((o) => o.value === e)?.label ?? e
}

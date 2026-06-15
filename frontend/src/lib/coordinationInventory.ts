import type { CoordinationInventory } from '../api/structuralAnalysis'

export function formatCoordinationInventorySummary(inventory: CoordinationInventory): string {
  const parts = inventory.discipline_lines
    .filter((line) => line.count > 0)
    .map((line) => `${line.count} ${line.short}`)

  if (parts.length === 0 && inventory.summary.sin_clasificar > 0) {
    return `${inventory.summary.sin_clasificar} sin clasificar (${inventory.summary.total_cad} CAD)`
  }

  const tail =
    inventory.summary.sin_clasificar > 0
      ? ` · ${inventory.summary.sin_clasificar} sin clasificar`
      : ''

  return `Inventario: ${parts.join(' · ')}${tail} (${inventory.summary.total_cad} CAD)`
}

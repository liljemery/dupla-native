/** Recomputes cantidad_total from cantidad_estimada and desperdicio (percentage). */
export function materialCantidadTotal(
  cantidadEstimada: number | null | undefined,
  desperdicioPorcentaje: number | null | undefined,
): number | null {
  if (cantidadEstimada == null || Number.isNaN(Number(cantidadEstimada))) return null
  const qty = Number(cantidadEstimada)
  const waste = desperdicioPorcentaje == null || Number.isNaN(Number(desperdicioPorcentaje)) ? 0 : Number(desperdicioPorcentaje)
  const total = qty * (1 + waste / 100)
  return Math.round(total * 1000) / 1000
}

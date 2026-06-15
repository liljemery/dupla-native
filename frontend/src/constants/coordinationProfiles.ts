export const COORDINATION_PROFILE_OPTIONS = [
  { value: '', label: '— Seleccionar edificio / registro —' },
  {
    value: 'tortuga_c40',
    label: 'Edificio TORTUGA (C-40)',
    hint: 'Planos del proyecto TORTUGA C-40 (registro de niveles Dupla).',
  },
  {
    value: 'serena18',
    label: 'Edificio SERENA (18)',
    hint: 'Planos del proyecto SERENA 18.',
  },
  {
    value: 'nasas09',
    label: 'Edificio NASAS (09)',
    hint: 'Planos del proyecto NASAS 09.',
  },
] as const

export function coordinationProfileLabel(slug: string | null | undefined): string {
  if (!slug) return 'Sin configurar'
  const hit = COORDINATION_PROFILE_OPTIONS.find((o) => o.value === slug)
  return hit?.label ?? slug
}

export function coordinationProfileHint(slug: string | null | undefined): string | null {
  if (!slug) return null
  const hit = COORDINATION_PROFILE_OPTIONS.find((o) => o.value === slug)
  return hit && 'hint' in hit ? hit.hint : null
}

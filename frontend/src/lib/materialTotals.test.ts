import { describe, expect, it } from 'vitest'

import { materialCantidadTotal } from './materialTotals'

describe('materialCantidadTotal', () => {
  it('applies waste percentage', () => {
    expect(materialCantidadTotal(50, 5)).toBe(52.5)
  })
  it('treats null waste as 0', () => {
    expect(materialCantidadTotal(50, null)).toBe(50)
  })
  it('returns null when qty missing', () => {
    expect(materialCantidadTotal(null, 5)).toBeNull()
  })
})

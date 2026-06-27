import type { BudgetRow } from '../types/budget'

export type ProcessedBudgetRow = BudgetRow & {
  computed_amount?: number
  computed_unit_price?: number
  computed_quantity?: number | string | null
}

export function processBudgetRows(rows: BudgetRow[]): ProcessedBudgetRow[] {
  const newRows = rows.map((r) => ({ ...r })) as ProcessedBudgetRow[]

  for (const r of newRows) {
    if (r.row_type === 'line') {
      const qty = Number(r.quantity) || 0
      const price = Number(r.unit_price) || 0
      r.computed_amount = qty * price
    }
  }
  for (const r of newRows) {
    if (r.row_type === 'subtotal') {
      const indices = r.metadata?.source_row_indices || []
      if (r.metadata?.manual_amount) {
        r.computed_amount = Number(r.amount) || 0
      } else {
        r.computed_amount = indices.reduce(
          (sum: number, idx: number) => sum + (newRows[idx]?.computed_amount || 0),
          0,
        )
      }
      r.computed_unit_price = r.computed_amount
      r.computed_quantity = 1
    }
  }
  for (const r of newRows) {
    if (r.row_type === 'chapter') {
      const subIdx = r.metadata?.subtotal_row_index
      if (r.metadata?.manual_amount) {
        r.computed_amount = Number(r.amount) || 0
      } else if (typeof subIdx === 'number' && newRows[subIdx]) {
        r.computed_amount = newRows[subIdx].computed_amount
        r.computed_unit_price = newRows[subIdx].computed_unit_price
        r.computed_quantity = newRows[subIdx].computed_quantity
      } else if (typeof r.amount === 'number' && r.amount > 0) {
        r.computed_amount = r.amount
      } else {
        r.computed_amount = 0
      }
    }
  }
  return newRows
}

/** Persistable rows: sync amount from computed totals. */
export function rowsForSave(processed: ProcessedBudgetRow[]): BudgetRow[] {
  return processed.map((r) => {
    const amount =
      r.row_type === 'line'
        ? r.computed_amount ?? Number(r.quantity || 0) * Number(r.unit_price || 0)
        : ((r.computed_amount ?? Number(r.amount)) || 0)
    return {
      ...r,
      amount: Math.round((amount || 0) * 100) / 100,
      quantity: r.row_type === 'line' ? Number(r.quantity) || 0 : r.quantity,
      unit_price: r.row_type === 'line' ? Number(r.unit_price) || 0 : r.unit_price,
    }
  })
}

export function newBlankBudgetLine(): BudgetRow {
  return {
    row_type: 'line',
    code: '',
    nat: '',
    unit: 'ud',
    summary: '',
    quantity: 1,
    unit_price: 0,
    amount: 0,
  }
}

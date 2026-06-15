/** Demo local del presupuesto maestro (takeoff). Sin persistencia; «Recalcular» aleatoriza para maquetar la futura API. */

export const DOP_PER_USD = 56.85

export type DemoBudgetRowKind = 'section' | 'item' | 'discount'

export type DemoBudgetRow = {
  id: string
  sectionKey: string
  kind: DemoBudgetRowKind
  /** Código visible tipo PRE-01, 1.01 */
  code: string
  description: string
  qty: number | null
  unit: string
  unitDop: number
  unitUsd: number
}

export type LiquidacionRates = {
  seguroPct: number
  gastosAdminPct: number
  transportePct: number
  direccionTecnicaPct: number
  itbisPct: number
}

export const DEFAULT_LIQUIDACION_RATES: LiquidacionRates = {
  seguroPct: 2,
  gastosAdminPct: 8,
  transportePct: 3,
  direccionTecnicaPct: 5,
  itbisPct: 18,
}

export function cloneBudgetRows(rows: DemoBudgetRow[]): DemoBudgetRow[] {
  return rows.map((r) => ({ ...r }))
}

export function lineTotalDop(r: DemoBudgetRow): number {
  if (r.kind === 'section') return 0
  if (r.qty == null) return 0
  return r.qty * r.unitDop
}

export function lineTotalUsd(r: DemoBudgetRow): number {
  if (r.kind === 'section') return 0
  if (r.qty == null) return 0
  return r.qty * r.unitUsd
}

export function directSubtotalDop(rows: DemoBudgetRow[]): number {
  let s = 0
  for (const r of rows) {
    if (r.kind === 'item' || r.kind === 'discount') s += lineTotalDop(r)
  }
  return s
}

/** Aleatoriza cantidades y precios unitarios de ítems y descuentos (mock hasta conectar API). */
export function randomizeBudgetRows(rows: DemoBudgetRow[]): DemoBudgetRow[] {
  return rows.map((r) => {
    if (r.kind === 'section') return r
    const priceFactor = 0.88 + Math.random() * 0.26
    const nextUnitDop = Math.max(0.01, Math.round(r.unitDop * priceFactor * 100) / 100)
    const nextUnitUsd = Math.round((nextUnitDop / DOP_PER_USD) * 10000) / 10000
    if (r.kind === 'discount') {
      const sign = r.unitDop < 0 ? -1 : 1
      const mag = Math.abs(nextUnitDop)
      const bumped = Math.round(mag * (0.75 + Math.random() * 0.55) * 100) / 100
      const ud = sign * bumped
      return {
        ...r,
        unitDop: ud,
        unitUsd: Math.round((ud / DOP_PER_USD) * 10000) / 10000,
      }
    }
    const qtyFactor = 0.82 + Math.random() * 0.36
    const nextQty =
      r.qty != null ? Math.max(0.01, Math.round(r.qty * qtyFactor * 100) / 100) : r.qty
    return {
      ...r,
      qty: nextQty,
      unitDop: nextUnitDop,
      unitUsd: nextUnitUsd,
    }
  })
}

export type ScenarioRoll = {
  id: string
  title: string
  tagline: string
  totalDop: number
  pctVsBase: number
  recommended?: boolean
}

export function rollExecutionScenarios(directDop: number): ScenarioRoll[] {
  if (!Number.isFinite(directDop) || directDop <= 0) {
    return [
      {
        id: 'c',
        title: 'Conservador',
        tagline: 'Reserva ante imprevistos de obra y variaciones de materiales.',
        totalDop: 0,
        pctVsBase: 0,
      },
      {
        id: 'm',
        title: 'Moderado',
        tagline: 'Equilibrio entre precio competitivo y margen operativo.',
        totalDop: 0,
        pctVsBase: 0,
        recommended: true,
      },
      {
        id: 'p',
        title: 'Pro High-End',
        tagline: 'Especificaciones premium y mayor contingencia en acabados.',
        totalDop: 0,
        pctVsBase: 0,
      },
    ]
  }
  const cMul = 1.06 + Math.random() * 0.09
  const mMul = 0.94 + Math.random() * 0.08
  const pMul = 1.14 + Math.random() * 0.1
  const base = directDop
  return [
    {
      id: 'c',
      title: 'Conservador',
      tagline: 'Reserva ante imprevistos de obra y variaciones de materiales.',
      totalDop: Math.round(base * cMul * 100) / 100,
      pctVsBase: Math.round((cMul - 1) * 1000) / 10,
    },
    {
      id: 'm',
      title: 'Moderado',
      tagline: 'Equilibrio entre precio competitivo y margen operativo.',
      totalDop: Math.round(base * mMul * 100) / 100,
      pctVsBase: Math.round((mMul - 1) * 1000) / 10,
      recommended: true,
    },
    {
      id: 'p',
      title: 'Pro High-End',
      tagline: 'Especificaciones premium y mayor contingencia en acabados.',
      totalDop: Math.round(base * pMul * 100) / 100,
      pctVsBase: Math.round((pMul - 1) * 1000) / 10,
    },
  ]
}

export function aiSavingsHintDop(directDop: number): number {
  const base = Math.max(0, directDop)
  return Math.round(base * (0.008 + Math.random() * 0.015) * 100) / 100
}

export function seedBudgetRowsForProject(projectName: string): DemoBudgetRow[] {
  const pn = projectName.trim() || 'Proyecto'
  return [
    {
      id: 's1',
      sectionKey: 'pre',
      kind: 'section',
      code: '1.0',
      description: `PRELIMINARES Y TERRACERÍAS · ${pn}`,
      qty: null,
      unit: '',
      unitDop: 0,
      unitUsd: 0,
    },
    {
      id: 'l101',
      sectionKey: 'pre',
      kind: 'item',
      code: 'PRE-01',
      description: 'Trazo, niveles y replanteo general de obra',
      qty: 1,
      unit: 'lot',
      unitDop: 18500,
      unitUsd: Math.round((18500 / DOP_PER_USD) * 100) / 100,
    },
    {
      id: 'l102',
      sectionKey: 'pre',
      kind: 'item',
      code: 'PRE-02',
      description: 'Movimiento tierra selectiva y evacuación de material',
      qty: 420,
      unit: 'm3',
      unitDop: 385,
      unitUsd: Math.round((385 / DOP_PER_USD) * 10000) / 10000,
    },
    {
      id: 's2',
      sectionKey: 'cim',
      kind: 'section',
      code: '2.0',
      description: 'CIMENTACIÓN Y ESTRUCTURA',
      qty: null,
      unit: '',
      unitDop: 0,
      unitUsd: 0,
    },
    {
      id: 'l201',
      sectionKey: 'cim',
      kind: 'item',
      code: 'CIM-01',
      description: 'Hormigón armado HA-25 zapatas y pedestales',
      qty: 185,
      unit: 'm3',
      unitDop: 14250,
      unitUsd: Math.round((14250 / DOP_PER_USD) * 100) / 100,
    },
    {
      id: 'l202',
      sectionKey: 'cim',
      kind: 'item',
      code: 'CIM-02',
      description: 'Acero corrugado B500-S según planos estructurales',
      qty: 12400,
      unit: 'kg',
      unitDop: 92,
      unitUsd: Math.round((92 / DOP_PER_USD) * 10000) / 10000,
    },
    {
      id: 's3',
      sectionKey: 'arq',
      kind: 'section',
      code: '3.0',
      description: 'ARQUITECTURA · ACABADOS Y REVESTIMIENTOS',
      qty: null,
      unit: '',
      unitDop: 0,
      unitUsd: 0,
    },
    {
      id: 'l301',
      sectionKey: 'arq',
      kind: 'item',
      code: '3.01',
      description: 'Microcemento sistema continuo áreas húmedas (suministro y colocación)',
      qty: 280,
      unit: 'm2',
      unitDop: 2850,
      unitUsd: Math.round((2850 / DOP_PER_USD) * 100) / 100,
    },
    {
      id: 'l302',
      sectionKey: 'arq',
      kind: 'item',
      code: '3.02',
      description: 'Pintura vinílica premium muros y cielos interiores',
      qty: 1450,
      unit: 'm2',
      unitDop: 185,
      unitUsd: Math.round((185 / DOP_PER_USD) * 10000) / 10000,
    },
    {
      id: 'l303',
      sectionKey: 'arq',
      kind: 'item',
      code: '3.03',
      description: 'Revestimiento cerámico formato grande zonas sociales',
      qty: 620,
      unit: 'm2',
      unitDop: 2450,
      unitUsd: Math.round((2450 / DOP_PER_USD) * 100) / 100,
    },
    {
      id: 'l304',
      sectionKey: 'arq',
      kind: 'item',
      code: '3.04',
      description: 'Áreas exteriores · imprimación y pintura elastomérica',
      qty: 890,
      unit: 'm2',
      unitDop: 425,
      unitUsd: Math.round((425 / DOP_PER_USD) * 10000) / 10000,
    },
    {
      id: 'l305',
      sectionKey: 'arq',
      kind: 'item',
      code: '3.05',
      description: 'Piscina · impermeabilización + pasta cerámica y equipamiento skimmer',
      qty: 1,
      unit: 'lot',
      unitDop: 385000,
      unitUsd: Math.round((385000 / DOP_PER_USD) * 100) / 100,
    },
    {
      id: 'd1',
      sectionKey: 'arq',
      kind: 'discount',
      code: 'DESC',
      description: 'Crédito por partidas de microcemento presupuesto anterior (ajuste neto)',
      qty: 1,
      unit: 'ud',
      unitDop: -58500,
      unitUsd: Math.round((-58500 / DOP_PER_USD) * 100) / 100,
    },
    {
      id: 's4',
      sectionKey: 'mep',
      kind: 'section',
      code: '4.0',
      description: 'INSTALACIONES MEP Y ESPECIALES',
      qty: null,
      unit: '',
      unitDop: 0,
      unitUsd: 0,
    },
    {
      id: 'l401',
      sectionKey: 'mep',
      kind: 'item',
      code: 'MEP-01',
      description: 'Tableros, canalizaciones principales y puntos eléctricos según plano',
      qty: 1,
      unit: 'lot',
      unitDop: 428000,
      unitUsd: Math.round((428000 / DOP_PER_USD) * 100) / 100,
    },
    {
      id: 'l402',
      sectionKey: 'mep',
      kind: 'item',
      code: 'MEP-02',
      description: 'Sanitaria y fixtures baños / cocina (suministro instalación)',
      qty: 1,
      unit: 'lot',
      unitDop: 312500,
      unitUsd: Math.round((312500 / DOP_PER_USD) * 100) / 100,
    },
  ]
}

export const SECTION_FILTER_LABELS: Record<string, string> = {
  all: 'Todas las partidas',
  pre: '1.0 Preliminares',
  cim: '2.0 Cimentación',
  arq: '3.0 Arquitectura',
  mep: '4.0 Instalaciones',
}

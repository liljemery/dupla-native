export const BUSINESS_PLIEGO_SECTION_KEYS = [
  'scope',
  'technical_specifications',
  'materials',
  'construction_systems',
  'restrictions',
  'base_assumptions',
  'exclusions',
  'validated_documentation',
  'identified_risks',
] as const

export type BusinessPliegoSectionKey = (typeof BUSINESS_PLIEGO_SECTION_KEYS)[number]

export const BUSINESS_PLIEGO_SECTION_LABELS: Record<BusinessPliegoSectionKey, string> = {
  scope: 'Alcance del proyecto',
  technical_specifications: 'Especificaciones técnicas',
  materials: 'Materiales definidos',
  construction_systems: 'Sistemas constructivos',
  restrictions: 'Restricciones',
  base_assumptions: 'Supuestos base',
  exclusions: 'Exclusiones',
  validated_documentation: 'Documentación validada',
  identified_risks: 'Riesgos identificados',
}

export const MIN_PLIEGO_SECTION_LEN = 10

export function emptyBusinessPliegoSections(): Record<BusinessPliegoSectionKey, string> {
  return Object.fromEntries(BUSINESS_PLIEGO_SECTION_KEYS.map((k) => [k, ''])) as Record<
    BusinessPliegoSectionKey,
    string
  >
}

export function parseBusinessPliegoFromSpec(spec: Record<string, unknown> | undefined): {
  sections: Record<BusinessPliegoSectionKey, string>
  approved: boolean
  generatedAt: string | null
} {
  const base = emptyBusinessPliegoSections()
  if (!spec || typeof spec !== 'object') {
    return { sections: base, approved: false, generatedAt: null }
  }
  const ga = spec.ga_fo_01_arquitectura
  let gaApproved = false
  let gaApprovedAt: string | null = null
  if (ga && typeof ga === 'object') {
    const g = ga as Record<string, unknown>
    gaApproved = Boolean(g.approved)
    gaApprovedAt = typeof g.approved_at === 'string' ? g.approved_at : null
  }

  const bp = spec.business_pliego
  if (!bp || typeof bp !== 'object') {
    return { sections: base, approved: gaApproved, generatedAt: gaApprovedAt }
  }
  const b = bp as Record<string, unknown>
  const raw = b.sections
  const sections = { ...base }
  if (raw && typeof raw === 'object') {
    for (const k of BUSINESS_PLIEGO_SECTION_KEYS) {
      const v = (raw as Record<string, unknown>)[k]
      sections[k] = typeof v === 'string' ? v : v != null ? String(v) : ''
    }
  }
  const g = b.generated_at
  const bpApproved = Boolean(b.approved)
  const genAt = typeof g === 'string' ? g : null
  return {
    sections,
    approved: bpApproved || gaApproved,
    generatedAt: genAt ?? gaApprovedAt,
  }
}

export function isBusinessPliegoReady(
  sections: Record<BusinessPliegoSectionKey, string>,
  approved: boolean,
): boolean {
  const allSections = BUSINESS_PLIEGO_SECTION_KEYS.every(
    (k) => (sections[k]?.trim().length ?? 0) >= MIN_PLIEGO_SECTION_LEN,
  )
  return allSections && approved
}

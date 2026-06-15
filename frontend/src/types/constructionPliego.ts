export type ConstructionLineValue = {
  unidad: string
  cantidad: string
  unitario: string
}

export type ConstructionPliegoPersisted = {
  schema_version: 1
  lines: Record<string, ConstructionLineValue>
  approved_chapters?: Record<string, { approved_at: string }>
}

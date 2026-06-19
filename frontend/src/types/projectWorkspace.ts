export type ProjectFileRow = {
  uuid: string
  original_name: string
  mime: string | null
  category: string | null
  folder_uuid: string | null
  description: string | null
  discipline: string | null
  discipline_classifying?: boolean
  ingest_status: string
  counts_for_budget: boolean
  created_at: string
}

/** Respuesta de GET .../files/search (incluye ruta desde Raíz). */
export type ProjectFileSearchRow = ProjectFileRow & {
  path: string
}

export type ProjectFileFolderRow = {
  uuid: string
  name: string
  parent_uuid: string | null
  created_at: string
}

export type RevisionRow = {
  uuid: string
  version: number
  revision_role: string
  decision: string
  notes: string | null
  created_at: string
}

export type SubcontractLine = {
  uuid: string
  item_label: string
  provider: string | null
  price: string
  currency: string
}

export type SubcontractQuoteRow = {
  uuid: string
  title: string | null
  created_at: string
  lines: SubcontractLine[]
}

export type TechnicalFindingRow = {
  uuid: string
  discipline: string
  severity: string
  title: string
  description: string
  evidence_ref: string | null
  created_at: string
  created_by_user_uuid: string | null
}

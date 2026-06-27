import { describe, expect, it } from 'vitest'

import { hasGerenciaRevisionSinceManagementPhase } from './managementApprovalReview'
import type { RevisionRow } from '../types/projectWorkspace'

const gerenciaRev: RevisionRow = {
  uuid: '00000000-0000-4000-8000-000000000001',
  version: 1,
  revision_role: 'GERENCIA',
  decision: 'APPROVED',
  notes: null,
  created_at: '2026-06-15T10:00:00.000Z',
}

describe('hasGerenciaRevisionSinceManagementPhase', () => {
  it('requires GERENCIA revision after management_approval_entered_at', () => {
    const meta = { management_approval_entered_at: '2026-06-15T09:00:00.000Z' }
    expect(
      hasGerenciaRevisionSinceManagementPhase([gerenciaRev], meta, 'MANAGEMENT_APPROVAL'),
    ).toBe(true)
    expect(
      hasGerenciaRevisionSinceManagementPhase(
        [{ ...gerenciaRev, revision_role: 'CONTROL' }],
        meta,
        'MANAGEMENT_APPROVAL',
      ),
    ).toBe(false)
    expect(
      hasGerenciaRevisionSinceManagementPhase(
        [{ ...gerenciaRev, created_at: '2026-06-15T08:00:00.000Z' }],
        meta,
        'MANAGEMENT_APPROVAL',
      ),
    ).toBe(false)
  })

  it('legacy MANAGEMENT_APPROVAL without timestamp accepts any GERENCIA revision', () => {
    expect(hasGerenciaRevisionSinceManagementPhase([gerenciaRev], {}, 'MANAGEMENT_APPROVAL')).toBe(
      true,
    )
  })
})

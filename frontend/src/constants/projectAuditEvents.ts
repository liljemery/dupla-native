import { WORKFLOW_PHASE_LABELS } from './workflowPhases'

/** Etiquetas legibles para `project_events.event_type`. */
export const PROJECT_EVENT_LABELS: Record<string, string> = {
  PROJECT_CREATED: 'Proyecto creado',
  PROJECT_META_UPDATED: 'Metadatos del proyecto actualizados',
  PROJECT_MEMBERS_UPDATED: 'Equipo del proyecto actualizado',
  WORKFLOW_TRANSITION: 'Cambio de fase',
  BOOTSTRAP_UPDATED: 'Checklist de arranque actualizado',
  SPECIFICATIONS_UPDATED: 'Pliego de condiciones guardado',
  WORKFLOW_META_PATCHED: 'Metadatos de flujo (presupuesto) actualizados',
  ARCHITECTURE_SAVED: 'Documento arquitectónico guardado',
  ARCHITECTURE_REVISION: 'Revisión de arquitectura registrada',
  FILE_UPLOADED: 'Archivo subido',
  FILE_UPDATED: 'Archivo actualizado',
  FILE_DELETED: 'Archivo eliminado',
  TASK_CARD_CREATED: 'Tarea creada en el tablero',
  TASK_CARD_UPDATED: 'Tarea actualizada',
  TASK_CARD_LINKED: 'Tarea vinculada al proyecto',
  TASK_CARD_UNLINKED: 'Tarea desvinculada del proyecto',
  PLAN_DELIVERY_CREATED: 'Solicitud de entrega de planos (SDP)',
  PLAN_DELIVERY_UPDATED: 'Solicitud SDP actualizada',
  PLAN_DELIVERY_DELETED: 'Solicitud SDP eliminada',
  SUBCONTRACT_QUOTE_CREATED: 'Cotización de subcontrato creada',
  SUBCONTRACT_LINE_ADDED: 'Línea de subcontrato agregada',
  SUBCONTRACT_QUOTE_DELETED: 'Cotización de subcontrato eliminada',
  NOTIFICATION_ARCHITECTURE_COMPLETE: 'Notificación enviada (arquitectura)',
  NOTIFICATION_BUDGET_APPROVED: 'Notificación enviada (presupuesto aprobado)',
}

function phaseLabel(code: string | undefined): string {
  if (!code) return '—'
  return WORKFLOW_PHASE_LABELS[code] ?? code
}

export function humanizeProjectEvent(eventType: string): string {
  return PROJECT_EVENT_LABELS[eventType] ?? eventType
}

type Payload = Record<string, unknown>

function linesForPayload(eventType: string, payload: Payload): string[] {
  const out: string[] = []
  switch (eventType) {
    case 'WORKFLOW_TRANSITION': {
      const fromP = (payload.from_phase as string) ?? ''
      const toP = (payload.to_phase as string) ?? ''
      const dir = payload.direction === 'backward' ? 'Retroceso' : 'Avance'
      out.push(`${dir}: ${phaseLabel(fromP)} → ${phaseLabel(toP)}`)
      break
    }
    case 'PROJECT_CREATED':
      out.push(`Nombre: ${String(payload.name ?? '')}`)
      if (payload.client_name != null && String(payload.client_name).length > 0) {
        out.push(`Cliente: ${String(payload.client_name)}`)
      }
      break
    case 'PROJECT_META_UPDATED': {
      const name = payload.name as { from?: string; to?: string } | undefined
      if (name?.from != null || name?.to != null) {
        out.push(`Nombre: «${name?.from ?? ''}» → «${name?.to ?? ''}»`)
      }
      const client = payload.client_name as { from?: string | null; to?: string | null } | undefined
      if (client?.from != null || client?.to != null) {
        out.push(`Cliente: «${client?.from ?? '—'}» → «${client?.to ?? '—'}»`)
      }
      const ru = payload.responsible_user_uuid as { from?: string | null; to?: string | null } | undefined
      if (ru?.from != null || ru?.to != null) {
        out.push(`Responsable interno: «${ru?.from ?? '—'}» → «${ru?.to ?? '—'}»`)
      }
      const ren = payload.responsible_external_name as { from?: string | null; to?: string | null } | undefined
      if (ren?.from != null || ren?.to != null) {
        out.push(`Responsable externo (nombre): «${ren?.from ?? '—'}» → «${ren?.to ?? '—'}»`)
      }
      const ree = payload.responsible_external_email as { from?: string | null; to?: string | null } | undefined
      if (ree?.from != null || ree?.to != null) {
        out.push(`Responsable externo (correo): «${ree?.from ?? '—'}» → «${ree?.to ?? '—'}»`)
      }
      break
    }
    case 'PROJECT_MEMBERS_UPDATED':
      out.push(`Miembros: ${String(payload.member_count ?? 0)}`)
      break
    case 'SPECIFICATIONS_UPDATED':
      out.push(`Resumen: ${String(payload.summary_chars ?? 0)} caracteres`)
      break
    case 'WORKFLOW_META_PATCHED':
      out.push(`Campos: ${(payload.keys as string[])?.join(', ') ?? '—'}`)
      break
    case 'ARCHITECTURE_SAVED':
      out.push(`Grupos: ${String(payload.groups_count ?? 0)}, materiales: ${String(payload.materiales_count ?? 0)}`)
      break
    case 'ARCHITECTURE_REVISION':
      out.push(`Versión ${String(payload.version ?? '')}, decisión: ${String(payload.decision ?? '')}`)
      break
    case 'FILE_UPLOADED':
      out.push(`Archivo: ${String(payload.name ?? '')}`)
      break
    case 'FILE_UPDATED': {
      out.push(`Archivo: ${String(payload.name ?? '')}`)
      const ch = payload.changes as Record<string, { from?: unknown; to?: unknown }> | undefined
      if (ch?.original_name) {
        const o = ch.original_name
        out.push(`Nombre: «${String(o.from ?? '')}» → «${String(o.to ?? '')}»`)
      }
      if (ch?.description) {
        out.push('Descripción modificada')
      }
      if (ch?.discipline) {
        const d = ch.discipline
        out.push(`Disciplina: ${String(d.from ?? '—')} → ${String(d.to ?? '—')}`)
      }
      if (ch?.folder_uuid) {
        out.push('Ubicación (carpeta) modificada')
      }
      if (ch?.ingest_status) {
        const s = ch.ingest_status
        out.push(`Estado: ${String(s.from ?? '')} → ${String(s.to ?? '')}`)
      }
      break
    }
    case 'FILE_DELETED':
      out.push(`Archivo: ${String(payload.name ?? '')}`)
      break
    case 'BOOTSTRAP_UPDATED':
      out.push(`Ítems en checklist: ${String(payload.items ?? '')}`)
      break
    case 'TASK_CARD_CREATED':
      out.push(`Tarea: ${String(payload.title ?? '')}`)
      if (payload.list_title) out.push(`Columna: ${String(payload.list_title)}`)
      if (payload.created_in_phase) out.push(`Fase al crear: ${phaseLabel(String(payload.created_in_phase))}`)
      break
    case 'TASK_CARD_UPDATED': {
      const changes = payload.changes as Record<string, unknown> | undefined
      if (changes?.list) {
        const l = changes.list as Record<string, string>
        out.push(`Columna: ${l.from_list_title ?? ''} → ${l.to_list_title ?? ''}`)
      }
      if (changes?.title) {
        const t = changes.title as { from?: string; to?: string }
        out.push(`Título: «${t.from ?? ''}» → «${t.to ?? ''}»`)
      }
      if (changes?.archived) {
        const a = changes.archived as { from?: boolean; to?: boolean }
        out.push(`Archivada: ${a.from ? 'sí' : 'no'} → ${a.to ? 'sí' : 'no'}`)
      }
      if (changes?.assignee_uuid) {
        const a = changes.assignee_uuid as { from?: string | null; to?: string | null }
        out.push(`Asignado: ${a.from ?? '—'} → ${a.to ?? '—'}`)
      }
      break
    }
    case 'TASK_CARD_LINKED':
      out.push(`Tarea: ${String(payload.title ?? '')}`)
      if (payload.list_title) out.push(`Columna: ${String(payload.list_title)}`)
      break
    case 'TASK_CARD_UNLINKED':
      out.push(`Tarea: ${String(payload.title ?? '')}`)
      break
    case 'PLAN_DELIVERY_CREATED':
    case 'PLAN_DELIVERY_UPDATED':
    case 'PLAN_DELIVERY_DELETED':
      out.push(`${String(payload.request_number ?? '')} — ${String(payload.description ?? '').slice(0, 120)}`)
      break
    case 'SUBCONTRACT_QUOTE_CREATED':
    case 'SUBCONTRACT_QUOTE_DELETED':
      out.push(`Cotización: ${String(payload.title ?? '—')}`)
      break
    case 'SUBCONTRACT_LINE_ADDED':
      out.push(`${String(payload.item_label ?? '')} — ${String(payload.price ?? '')} ${String(payload.currency ?? '')}`)
      break
    case 'NOTIFICATION_ARCHITECTURE_COMPLETE':
    case 'NOTIFICATION_BUDGET_APPROVED':
      out.push(`Destinatarios: ${String(payload.recipient_count ?? 0)}`)
      break
    default:
      break
  }
  return out
}

/** Texto legible para auditoría; si no hay reglas, usa JSON compacto. */
export function describeProjectEventBody(eventType: string, payload: Payload): string {
  const lines = linesForPayload(eventType, payload)
  if (lines.length > 0) return lines.join('\n')
  try {
    return JSON.stringify(payload, null, 2)
  } catch {
    return String(payload)
  }
}

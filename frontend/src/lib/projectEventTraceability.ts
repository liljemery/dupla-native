import { projectKindLabel } from '../constants/projectKind'
import { WORKFLOW_PHASE_LABELS } from '../constants/workflowPhases'

export type ProjectEventRow = {
  uuid: string
  event_type: string
  payload: Record<string, unknown>
  actor_user_uuid: string | null
  actor_email: string | null
  created_at: string
}

export type ProjectEventTrace = {
  title: string
  rows: { label: string; value: string }[]
}

function phaseLabel(phase: string): string {
  return WORKFLOW_PHASE_LABELS[phase] ?? phase
}

function str(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function directionLabel(d: unknown): string {
  if (d === 'forward') return 'Adelante (siguiente fase)'
  if (d === 'backward') return 'Atrás (fase anterior)'
  return str(d)
}

export function describeProjectEvent(ev: ProjectEventRow): ProjectEventTrace {
  const p = ev.payload
  const rows: { label: string; value: string }[] = []

  switch (ev.event_type) {
    case 'WORKFLOW_TRANSITION': {
      const fromP = typeof p.from_phase === 'string' ? p.from_phase : ''
      const toP = typeof p.to_phase === 'string' ? p.to_phase : ''
      const fromTitle = typeof p.from_step_title === 'string' ? p.from_step_title.trim() : ''
      const toTitle = typeof p.to_step_title === 'string' ? p.to_step_title.trim() : ''
      const fromDisplay =
        fromTitle.length > 0 ? `${fromTitle} (${phaseLabel(fromP)})` : phaseLabel(fromP) || '—'
      const toDisplay =
        toTitle.length > 0 ? `${toTitle} (${phaseLabel(toP)})` : phaseLabel(toP) || '—'
      rows.push(
        { label: 'Paso origen', value: fromDisplay },
        { label: 'Paso destino', value: toDisplay },
        { label: 'Dirección', value: directionLabel(p.direction) },
      )
      return { title: 'Cambio de fase del proyecto', rows }
    }
    case 'PROJECT_CREATED': {
      rows.push(
        { label: 'Nombre', value: str(p.name) },
        { label: 'Cliente', value: str(p.client_name) },
        {
          label: 'Tipo',
          value: projectKindLabel(typeof p.project_kind === 'string' ? p.project_kind : undefined),
        },
      )
      return { title: 'Proyecto creado', rows }
    }
    case 'PROJECT_MEMBERS_UPDATED': {
      const n = typeof p.member_count === 'number' ? p.member_count : null
      if (n !== null) rows.push({ label: 'Participantes', value: String(n) })
      const members = p.members
      if (Array.isArray(members)) {
        const emails = members
          .map((m) => {
            if (m && typeof m === 'object' && 'email' in m) return String((m as { email: string }).email)
            return ''
          })
          .filter(Boolean)
        if (emails.length > 0) rows.push({ label: 'Correos', value: emails.join(', ') })
      }
      return { title: 'Equipo del proyecto actualizado', rows }
    }
    case 'PROJECT_META_UPDATED': {
      const nameField = p.name
      if (nameField && typeof nameField === 'object' && nameField !== null) {
        const o = nameField as { from?: unknown; to?: unknown }
        rows.push({ label: 'Nombre', value: `${str(o.from)} → ${str(o.to)}` })
      }
      const clientField = p.client_name
      if (clientField && typeof clientField === 'object' && clientField !== null) {
        const o = clientField as { from?: unknown; to?: unknown }
        rows.push({ label: 'Cliente', value: `${str(o.from)} → ${str(o.to)}` })
      }
      const ru = p.responsible_user_uuid
      if (ru && typeof ru === 'object' && ru !== null) {
        const o = ru as { from?: unknown; to?: unknown }
        rows.push({ label: 'Responsable interno (UUID)', value: `${str(o.from)} → ${str(o.to)}` })
      }
      const ren = p.responsible_external_name
      if (ren && typeof ren === 'object' && ren !== null) {
        const o = ren as { from?: unknown; to?: unknown }
        rows.push({ label: 'Responsable externo (nombre)', value: `${str(o.from)} → ${str(o.to)}` })
      }
      const ree = p.responsible_external_email
      if (ree && typeof ree === 'object' && ree !== null) {
        const o = ree as { from?: unknown; to?: unknown }
        rows.push({ label: 'Responsable externo (correo)', value: `${str(o.from)} → ${str(o.to)}` })
      }
      return { title: 'Datos del proyecto modificados', rows }
    }
    case 'BOOTSTRAP_UPDATED': {
      rows.push({ label: 'Ítems en checklist', value: str(p.items) })
      return { title: 'Checklist de arranque guardado', rows }
    }
    case 'SPECIFICATIONS_UPDATED': {
      rows.push({ label: 'Resumen (caracteres)', value: str(p.summary_chars) })
      return { title: 'Pliego de condiciones actualizado', rows }
    }
    case 'WORKFLOW_META_PATCHED': {
      const keys = p.keys
      rows.push({
        label: 'Campos tocados',
        value: Array.isArray(keys) ? keys.join(', ') : str(keys),
      })
      return { title: 'Metadatos de flujo / presupuesto', rows }
    }
    case 'ARCHITECTURE_REVISION': {
      rows.push(
        { label: 'Versión', value: str(p.version) },
        { label: 'Decisión', value: str(p.decision) },
      )
      return { title: 'Revisión de arquitectura registrada', rows }
    }
    case 'FILE_UPLOADED': {
      rows.push(
        { label: 'Archivo', value: str(p.name) },
        { label: 'ID archivo', value: str(p.file_uuid) },
      )
      return { title: 'Archivo subido al proyecto', rows }
    }
    case 'FILE_UPDATED': {
      rows.push(
        { label: 'Nombre mostrado', value: str(p.name) },
        { label: 'ID archivo', value: str(p.file_uuid) },
      )
      const ch = p.changes as Record<string, unknown> | undefined
      if (ch && typeof ch === 'object') {
        if (ch.original_name && typeof ch.original_name === 'object') {
          const o = ch.original_name as { from?: unknown; to?: unknown }
          rows.push({ label: 'Nombre', value: `${str(o.from)} → ${str(o.to)}` })
        }
        if (ch.description) rows.push({ label: 'Descripción', value: 'Actualizada' })
        if (ch.discipline && typeof ch.discipline === 'object') {
          const d = ch.discipline as { from?: unknown; to?: unknown }
          rows.push({ label: 'Disciplina', value: `${str(d.from)} → ${str(d.to)}` })
        }
        if (ch.folder_uuid) rows.push({ label: 'Carpeta', value: 'Movida o cambiada' })
        if (ch.ingest_status && typeof ch.ingest_status === 'object') {
          const s = ch.ingest_status as { from?: unknown; to?: unknown }
          rows.push({ label: 'Estado ingesta', value: `${str(s.from)} → ${str(s.to)}` })
        }
      }
      return { title: 'Metadatos de archivo actualizados', rows }
    }
    case 'FILE_DELETED': {
      rows.push(
        { label: 'Archivo', value: str(p.name) },
        { label: 'ID archivo', value: str(p.file_uuid) },
      )
      return { title: 'Archivo eliminado del proyecto', rows }
    }
    case 'ARCHITECTURE_SAVED': {
      rows.push(
        { label: 'Secciones / grupos', value: str(p.groups_count) },
        { label: 'Materiales', value: str(p.materiales_count) },
      )
      return { title: 'Pliego / cubicación guardados en el workspace', rows }
    }
    case 'NOTIFICATION_ARCHITECTURE_COMPLETE': {
      rows.push({ label: 'Destinatarios (aprox.)', value: str(p.recipient_count) })
      return { title: 'Notificación: arquitectura completada', rows }
    }
    case 'NOTIFICATION_BUDGET_APPROVED': {
      rows.push({ label: 'Destinatarios (aprox.)', value: str(p.recipient_count) })
      return { title: 'Notificación: presupuesto aprobado', rows }
    }
    case 'TASK_CARD_CREATED': {
      rows.push(
        { label: 'Tarea', value: str(p.title) },
        { label: 'Lista', value: str(p.list_title) },
        { label: 'Fase al crear', value: typeof p.created_in_phase === 'string' ? phaseLabel(p.created_in_phase) : str(p.created_in_phase) },
      )
      return { title: 'Tarea creada en el tablero', rows }
    }
    case 'TASK_CARD_LINKED': {
      rows.push(
        { label: 'Tarea', value: str(p.title) },
        { label: 'Columna', value: str(p.list_title) },
      )
      return { title: 'Tarea vinculada a este proyecto', rows }
    }
    case 'TASK_CARD_UNLINKED': {
      rows.push({ label: 'Tarea', value: str(p.title) })
      return { title: 'Tarea desvinculada de este proyecto', rows }
    }
    case 'TASK_CARD_UPDATED': {
      rows.push({ label: 'Tarea', value: str(p.title) })
      const changes = p.changes
      if (changes && typeof changes === 'object' && changes !== null) {
        const ch = changes as Record<string, unknown>
        if (ch.list) {
          const L = ch.list as Record<string, unknown>
          rows.push({
            label: 'Movimiento entre columnas',
            value: `${str(L.from_list_title)} → ${str(L.to_list_title)}`,
          })
        }
        if (ch.title) {
          const t = ch.title as { from?: unknown; to?: unknown }
          rows.push({ label: 'Título', value: `${str(t.from)} → ${str(t.to)}` })
        }
        if (ch.assignee_uuid) {
          const a = ch.assignee_uuid as { from?: unknown; to?: unknown }
          rows.push({ label: 'Asignación (UUID)', value: `${str(a.from)} → ${str(a.to)}` })
        }
        if (ch.archived) {
          const a = ch.archived as { from?: unknown; to?: unknown }
          rows.push({ label: 'Archivada', value: `${str(a.from)} → ${str(a.to)}` })
        }
        if (ch.description) {
          rows.push({ label: 'Descripción', value: 'Actualizada' })
        }
      }
      return { title: 'Tarea actualizada', rows }
    }
    case 'SUBCONTRACT_QUOTE_CREATED': {
      rows.push(
        { label: 'Cotización', value: str(p.title) },
        { label: 'ID', value: str(p.quote_uuid) },
      )
      return { title: 'Nueva cotización de subcontrato', rows }
    }
    case 'SUBCONTRACT_LINE_ADDED': {
      rows.push(
        { label: 'Ítem', value: str(p.item_label) },
        { label: 'Importe', value: `${str(p.price)} ${str(p.currency)}` },
      )
      return { title: 'Línea agregada a cotización', rows }
    }
    case 'SUBCONTRACT_QUOTE_DELETED': {
      rows.push({ label: 'Cotización', value: str(p.title) })
      return { title: 'Cotización eliminada', rows }
    }
    case 'PLAN_DELIVERY_CREATED': {
      rows.push(
        { label: 'No. solicitud', value: str(p.request_number) },
        { label: 'Descripción', value: str(p.description) },
      )
      return { title: 'Solicitud de entrega de planos creada', rows }
    }
    case 'PLAN_DELIVERY_UPDATED': {
      rows.push({ label: 'No. solicitud', value: str(p.request_number) })
      const ch = p.changes
      rows.push({
        label: 'Cambios',
        value:
          ch && typeof ch === 'object'
            ? JSON.stringify(ch as Record<string, unknown>, null, 2)
            : str(ch),
      })
      return { title: 'Solicitud de entrega de planos actualizada', rows }
    }
    case 'PLAN_DELIVERY_DELETED': {
      rows.push(
        { label: 'No. solicitud', value: str(p.request_number) },
        { label: 'Descripción', value: str(p.description) },
      )
      return { title: 'Solicitud de entrega de planos eliminada', rows }
    }
    default: {
      rows.push({ label: 'Tipo', value: ev.event_type })
      for (const [k, v] of Object.entries(p)) {
        rows.push({ label: k, value: str(v) })
      }
      return { title: 'Evento del proyecto', rows }
    }
  }
}

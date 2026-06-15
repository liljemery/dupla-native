/** Tipos de evento alineados con el backend (`record_event`). */
export const PROJECT_EVENT_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'ARCHITECTURE_REVISION', label: 'Revisión de arquitectura' },
  { value: 'ARCHITECTURE_SAVED', label: 'Pliego / cubicación guardados' },
  { value: 'BOOTSTRAP_UPDATED', label: 'Checklist de arranque' },
  { value: 'FILE_UPLOADED', label: 'Archivo subido' },
  { value: 'FILE_UPDATED', label: 'Archivo actualizado' },
  { value: 'FILE_DELETED', label: 'Archivo eliminado' },
  { value: 'NOTIFICATION_ARCHITECTURE_COMPLETE', label: 'Notificación: arquitectura' },
  { value: 'NOTIFICATION_BUDGET_APPROVED', label: 'Notificación: presupuesto' },
  { value: 'PLAN_DELIVERY_CREATED', label: 'Entrega de planos: creado' },
  { value: 'PLAN_DELIVERY_DELETED', label: 'Entrega de planos: eliminado' },
  { value: 'PLAN_DELIVERY_UPDATED', label: 'Entrega de planos: actualizado' },
  { value: 'PROJECT_CREATED', label: 'Proyecto creado' },
  { value: 'PROJECT_MEMBERS_UPDATED', label: 'Miembros del proyecto' },
  { value: 'PROJECT_META_UPDATED', label: 'Nombre / cliente del proyecto' },
  { value: 'SPECIFICATIONS_UPDATED', label: 'Pliego de condiciones' },
  { value: 'SUBCONTRACT_LINE_ADDED', label: 'Cotización: línea agregada' },
  { value: 'SUBCONTRACT_QUOTE_CREATED', label: 'Cotización creada' },
  { value: 'SUBCONTRACT_QUOTE_DELETED', label: 'Cotización eliminada' },
  { value: 'TASK_CARD_CREATED', label: 'Tarea: creada' },
  { value: 'TASK_CARD_LINKED', label: 'Tarea: vinculada' },
  { value: 'TASK_CARD_UNLINKED', label: 'Tarea: desvinculada' },
  { value: 'TASK_CARD_UPDATED', label: 'Tarea: actualizada' },
  { value: 'WORKFLOW_META_PATCHED', label: 'Metadatos flujo / presupuesto' },
  { value: 'WORKFLOW_TRANSITION', label: 'Cambio de fase' },
]

export function projectEventSearchPlaceholder(eventType: string): string {
  if (!eventType) {
    return 'Buscar en el detalle del evento o en el correo de quien lo realizó…'
  }
  if (eventType.startsWith('TASK_CARD')) {
    return 'Título de tarea, columna, UUID de tarea…'
  }
  if (
    eventType === 'PROJECT_CREATED' ||
    eventType === 'PROJECT_META_UPDATED' ||
    eventType === 'PROJECT_MEMBERS_UPDATED'
  ) {
    return 'Nombre, cliente, correos de miembros…'
  }
  if (eventType === 'WORKFLOW_TRANSITION') {
    return 'Fase origen o destino (texto o código), dirección…'
  }
  if (eventType === 'FILE_UPLOADED' || eventType === 'FILE_UPDATED' || eventType === 'FILE_DELETED') {
    return 'Nombre de archivo…'
  }
  if (eventType === 'ARCHITECTURE_REVISION') {
    return 'Decisión, versión…'
  }
  if (eventType === 'BOOTSTRAP_UPDATED' || eventType === 'SPECIFICATIONS_UPDATED') {
    return 'Texto relacionado al guardado…'
  }
  if (eventType === 'WORKFLOW_META_PATCHED') {
    return 'Claves de metadatos…'
  }
  if (eventType.startsWith('SUBCONTRACT_')) {
    return 'Título cotización, ítem, importe…'
  }
  if (eventType.startsWith('PLAN_DELIVERY_')) {
    return 'Número de solicitud, descripción…'
  }
  if (eventType.startsWith('NOTIFICATION_')) {
    return 'Detalle en payload o correo…'
  }
  if (eventType === 'ARCHITECTURE_SAVED') {
    return 'Cantidad de grupos o materiales…'
  }
  return 'Buscar en el detalle del evento o correo del autor…'
}

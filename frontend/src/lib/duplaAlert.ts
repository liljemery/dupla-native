import Swal from 'sweetalert2'

export interface DuplaAlertOptions {
  title: string
  text?: string
  confirmLabel?: string
  cancelLabel?: string
}

const duplaSwal = Swal.mixin({
  customClass: {
    popup: 'du-swal-popup',
    title: 'du-swal-title',
    htmlContainer: 'du-swal-text',
    confirmButton: 'du-swal-confirm',
    cancelButton: 'du-swal-cancel',
    actions: 'du-swal-actions',
    icon: 'du-swal-icon',
  },
  buttonsStyling: false,
  reverseButtons: true,
  focusCancel: true,
})

export async function confirmDestructive(options: DuplaAlertOptions): Promise<boolean> {
  const result = await duplaSwal.fire({
    icon: 'warning',
    title: options.title,
    text: options.text,
    showCancelButton: true,
    confirmButtonText: options.confirmLabel ?? 'Eliminar',
    cancelButtonText: options.cancelLabel ?? 'Cancelar',
  })
  return result.isConfirmed
}

export async function confirmAction(options: DuplaAlertOptions): Promise<boolean> {
  const result = await duplaSwal.fire({
    icon: 'question',
    title: options.title,
    text: options.text,
    showCancelButton: true,
    confirmButtonText: options.confirmLabel ?? 'Confirmar',
    cancelButtonText: options.cancelLabel ?? 'Cancelar',
  })
  return result.isConfirmed
}

export async function confirmPliegoSectionApproval(options: {
  sectionTitle: string
  costHint?: string
}): Promise<boolean> {
  const costLine =
    options.costHint ??
    'Al aprobar esta sección, su contenido se considerará validado y los costos asociados se asumirán como base para el presupuesto maestro del proyecto.'
  return confirmAction({
    title: `¿Aprobar «${options.sectionTitle}»?`,
    text: costLine,
    confirmLabel: 'Aprobar sección',
  })
}

export async function alertInfo(options: DuplaAlertOptions): Promise<void> {
  await duplaSwal.fire({
    icon: 'info',
    title: options.title,
    text: options.text,
    confirmButtonText: options.confirmLabel ?? 'Entendido',
  })
}

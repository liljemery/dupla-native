import type { ToastVariant } from './toastTypes'

type ToastEmitter = (message: string, variant?: ToastVariant) => void

let emitFn: ToastEmitter | null = null

export function registerToastEmitter(fn: ToastEmitter) {
  emitFn = fn
}

export function unregisterToastEmitter() {
  emitFn = null
}

export function emitToast(message: string, variant: ToastVariant = 'error') {
  emitFn?.(message, variant)
}

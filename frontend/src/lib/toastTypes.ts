export type ToastVariant = 'error' | 'warning' | 'success' | 'info'

export interface Toast {
  id: string
  message: string
  variant: ToastVariant
}

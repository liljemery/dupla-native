import { createContext } from 'react'

import type { ToastVariant } from './toastTypes'

export interface ToastContextValue {
  addToast: (message: string, variant?: ToastVariant) => void
}

export const ToastContext = createContext<ToastContextValue>({
  addToast: () => undefined,
})

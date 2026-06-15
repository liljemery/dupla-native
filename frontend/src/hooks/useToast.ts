import { useContext } from 'react'

import { ToastContext } from '../lib/toastContext'

export function useToast() {
  return useContext(ToastContext)
}

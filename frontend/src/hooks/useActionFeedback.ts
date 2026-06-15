import { useCallback, useEffect, useRef, useState } from 'react'

export type ActionFeedbackStatus = 'idle' | 'running' | 'success' | 'error'

const DEFAULT_RESET_MS = 2200

export function useActionFeedback(resetMs = DEFAULT_RESET_MS) {
  const [status, setStatus] = useState<ActionFeedbackStatus>('idle')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  const reset = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    setStatus('idle')
  }, [])

  const run = useCallback(
    async (action: () => Promise<boolean | void> | boolean | void): Promise<boolean> => {
      if (timerRef.current) clearTimeout(timerRef.current)
      setStatus('running')
      try {
        const result = await action()
        if (result === true) {
          setStatus('success')
          timerRef.current = setTimeout(() => setStatus('idle'), resetMs)
          return true
        }
        if (result === false) {
          setStatus('error')
          timerRef.current = setTimeout(() => setStatus('idle'), resetMs)
          return false
        }
        setStatus('idle')
        return false
      } catch {
        setStatus('error')
        timerRef.current = setTimeout(() => setStatus('idle'), resetMs)
        return false
      }
    },
    [resetMs],
  )

  return { status, run, reset, isBusy: status === 'running' }
}

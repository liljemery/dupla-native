import { useEffect, useId, useRef } from 'react'
import { X } from 'lucide-react'

type Props = {
  open: boolean
  title: string
  src: string
  onClose: () => void
}

export function TutorialVideoModal({ open, title, src, onClose }: Props) {
  const titleId = useId()
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    if (!open) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  useEffect(() => {
    if (open) return
    const video = videoRef.current
    if (!video) return
    video.pause()
    video.currentTime = 0
  }, [open])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="flex w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-black/10 bg-white shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <div className="flex items-center justify-between gap-3 border-b border-black/8 px-4 py-3 sm:px-5">
          <h2 id={titleId} className="min-w-0 truncate text-base font-semibold text-ink sm:text-lg">
            {title}
          </h2>
          <button
            type="button"
            className="shrink-0 rounded-lg p-1.5 text-muted outline-none transition-colors hover:bg-black/5 hover:text-ink focus-visible:ring-2 focus-visible:ring-primary/35"
            aria-label="Cerrar video"
            onClick={onClose}
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>
        <div className="bg-black">
          <video
            ref={videoRef}
            className="aspect-video w-full"
            src={src}
            controls
            playsInline
            preload="metadata"
          />
        </div>
      </div>
    </div>
  )
}

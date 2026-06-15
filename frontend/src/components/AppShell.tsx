import type { ReactNode } from 'react'

type Props = {
  header: ReactNode
  children: ReactNode
}

export function AppShell({ header, children }: Props) {
  return (
    <div className="min-h-screen bg-surface text-ink">
      {header}
      <div className="mx-auto max-w-6xl px-6 py-10">{children}</div>
    </div>
  )
}

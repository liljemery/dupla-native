import type { ReactNode } from 'react'

type MasterDetailLayoutProps = {
  master: ReactNode
  detail: ReactNode
  className?: string
}

export function MasterDetailLayout({ master, detail, className = '' }: MasterDetailLayoutProps) {
  return (
    <div className={`du-master-detail-shell ${className}`}>
      <div className="min-h-0 overflow-y-auto py-4 pl-4 pr-2">{master}</div>
      <div className="min-h-0 overflow-hidden rounded-l-[1.75rem] bg-panel-detail lg:rounded-l-[2rem]">
        {detail}
      </div>
    </div>
  )
}

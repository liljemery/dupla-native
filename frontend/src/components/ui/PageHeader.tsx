import type { ReactNode } from 'react'

type PageHeaderProps = {
  title: string
  subtitle?: string
  actions?: ReactNode
  titleExtra?: ReactNode
  toolbar?: ReactNode
}

export function PageHeader({ title, subtitle, actions, titleExtra, toolbar }: PageHeaderProps) {
  return (
    <header className="flex shrink-0 flex-col gap-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h1 className="du-page-title">{title}</h1>
            {titleExtra}
          </div>
          {subtitle ? (
            <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">{subtitle}</p>
          ) : null}
        </div>
        {toolbar ? (
          <div className="du-page-toolbar shrink-0">{toolbar}</div>
        ) : actions ? (
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">{actions}</div>
        ) : null}
      </div>
    </header>
  )
}

type PageToolbarItemProps = {
  children: ReactNode
}

export function PageToolbarItem({ children }: PageToolbarItemProps) {
  return <div className="flex items-center">{children}</div>
}

export function PageToolbarDivider() {
  return <span className="du-toolbar-divider" aria-hidden />
}

import type { ReactNode } from 'react'

export type TabItem = { id: string; label: string }

type Props = {
  tabs: TabItem[]
  value: string
  onChange: (id: string) => void
  children: ReactNode
  labelledBy?: string
}

export function Tabs({ tabs, value, onChange, children, labelledBy }: Props) {
  return (
    <div className="min-w-0">
      <div className="overflow-x-auto overflow-y-hidden border-b border-black/10 [scrollbar-width:thin]">
        <div
          className="flex min-w-0 flex-nowrap gap-1"
          role="tablist"
          aria-labelledby={labelledBy}
        >
        {tabs.map((t) => {
          const selected = t.id === value
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={selected}
              id={`tab-${t.id}`}
              tabIndex={selected ? 0 : -1}
              className={`relative -mb-px shrink-0 whitespace-nowrap border-b-2 px-4 py-2.5 text-base font-medium outline-none transition-colors duration-150 md:px-5 md:py-3.5 ${
                selected
                  ? 'border-primary bg-primary/[0.06] text-ink'
                  : 'border-transparent text-muted hover:bg-black/[0.04] hover:text-ink active:bg-black/[0.06]'
              } focus-visible:z-10 focus-visible:rounded-t-md focus-visible:ring-2 focus-visible:ring-primary/35 focus-visible:ring-offset-2 focus-visible:ring-offset-white`}
              onClick={() => onChange(t.id)}
            >
              {t.label}
            </button>
          )
        })}
        </div>
      </div>
      <div
        role="tabpanel"
        aria-labelledby={`tab-${value}`}
        className="pt-5 md:pt-7 lg:pt-9"
      >
        {children}
      </div>
    </div>
  )
}

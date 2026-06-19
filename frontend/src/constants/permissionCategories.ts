export type PermissionCategoryStyle = {
  border: string
  bg: string
  badge: string
  dot: string
}

/** Estilos por sección del catálogo RBAC — paleta Dupla. */
export const PERMISSION_CATEGORY_STYLE: Record<string, PermissionCategoryStyle> = {
  Admin: {
    border: 'border-l-primary',
    bg: 'bg-primary/6',
    badge: 'bg-primary/12 text-primary',
    dot: 'bg-primary',
  },
  Dashboard: {
    border: 'border-l-panel-detail',
    bg: 'bg-panel-detail/10',
    badge: 'bg-panel-detail/20 text-panel-detail',
    dot: 'bg-panel-detail',
  },
  Flujos: {
    border: 'border-l-ink',
    bg: 'bg-black/[0.03]',
    badge: 'bg-ink/10 text-ink',
    dot: 'bg-ink',
  },
  Proyectos: {
    border: 'border-l-primary-bright',
    bg: 'bg-primary/[0.04]',
    badge: 'bg-primary/10 text-primary-bright',
    dot: 'bg-primary-bright',
  },
  Presupuesto: {
    border: 'border-l-panel-charcoal',
    bg: 'bg-panel-charcoal/[0.06]',
    badge: 'bg-panel-charcoal/10 text-panel-charcoal',
    dot: 'bg-panel-charcoal',
  },
  'Ciclo de vida': {
    border: 'border-l-primary/70',
    bg: 'bg-primary/[0.05]',
    badge: 'bg-primary/8 text-primary',
    dot: 'bg-primary/80',
  },
  Workspace: {
    border: 'border-l-panel-dark-muted',
    bg: 'bg-surface-elevated',
    badge: 'bg-black/8 text-muted',
    dot: 'bg-panel-dark-muted',
  },
}

const FALLBACK_STYLE: PermissionCategoryStyle = {
  border: 'border-l-muted',
  bg: 'bg-surface',
  badge: 'bg-black/6 text-muted',
  dot: 'bg-muted',
}

export function permissionCategoryStyle(category: string): PermissionCategoryStyle {
  return PERMISSION_CATEGORY_STYLE[category] ?? FALLBACK_STYLE
}

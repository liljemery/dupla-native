import type { ComponentType } from 'react'
import type { LucideProps } from 'lucide-react'
import * as LucideIcons from 'lucide-react'

import {
  DEFAULT_FLOW_TEMPLATE_ICON,
  FLOW_TEMPLATE_ICON_KEYS,
  type FlowTemplateIconKey,
} from '../../constants/flowTemplateIcons'

type Props = {
  name: string | null | undefined
  className?: string
  strokeWidth?: LucideProps['strokeWidth']
}

export function FlowTemplateIcon({ name, className, strokeWidth = 2 }: Props) {
  const key = (
    name && (FLOW_TEMPLATE_ICON_KEYS as readonly string[]).includes(name) ? name : DEFAULT_FLOW_TEMPLATE_ICON
  ) as FlowTemplateIconKey
  const Cmp =
    (LucideIcons as unknown as Record<string, ComponentType<LucideProps>>)[key] ??
    LucideIcons.GitBranch
  return <Cmp className={className} strokeWidth={strokeWidth} aria-hidden />
}

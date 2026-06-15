type Props = {
  className?: string
}

export function DuplaSidebarLogo({
  className = 'h-10 w-auto max-w-[min(100%,320px)] object-contain object-left',
}: Props) {
  return <img src="/dupla-sidebar-logo.jpeg" alt="Grupo Dupla" className={className} />
}

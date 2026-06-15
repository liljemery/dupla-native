type Props = {
  className?: string
}

export function DuplaLogo({ className = 'h-12 w-auto max-w-[280px] object-contain object-left' }: Props) {
  return <img src="/logo-dupla.png" alt="Grupo Dupla" className={className} />
}

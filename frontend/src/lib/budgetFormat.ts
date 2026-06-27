export function fmtDop(n: unknown): string {
  const num = Number(n) || 0
  return new Intl.NumberFormat('es-DO', {
    style: 'currency',
    currency: 'DOP',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num)
}

export function fmtUsd(n: unknown, tcRate = 58.5): string {
  const num = Number(n) || 0
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num / tcRate)
}

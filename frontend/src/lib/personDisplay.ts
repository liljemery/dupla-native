/** Nombre legible para listas; si no hay nombre, el correo. */
export function formatPersonFullName(
  firstName: string | null | undefined,
  lastName: string | null | undefined,
  email: string,
): string {
  const f = (firstName ?? '').trim()
  const l = (lastName ?? '').trim()
  if (f && l) return `${f} ${l}`
  if (f) return f
  if (l) return l
  return email
}

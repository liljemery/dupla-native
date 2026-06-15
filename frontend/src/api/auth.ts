import { apiFetch } from './client'

export async function requestPasswordReset(email: string): Promise<string> {
  const res = await apiFetch('/api/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
  const body = (await res.json().catch(() => ({}))) as {
    detail?: string
    message?: string
    dev_reset_token?: string
  }
  if (!res.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : 'No se pudo enviar la solicitud'
    throw new Error(detail)
  }
  return body.message ?? 'Si el correo está registrado, recibirás un enlace para restablecer tu contraseña.'
}

export async function resetPassword(token: string, password: string): Promise<string> {
  const res = await apiFetch('/api/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ token, password }),
  })
  const body = (await res.json().catch(() => ({}))) as { detail?: string; message?: string }
  if (!res.ok) {
    throw new Error(body.detail ?? 'No se pudo restablecer la contraseña')
  }
  return body.message ?? 'Contraseña actualizada.'
}

export async function changePassword(
  token: string,
  currentPassword: string,
  newPassword: string,
): Promise<string> {
  const res = await apiFetch('/api/auth/change-password', {
    method: 'POST',
    token,
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  })
  const body = (await res.json().catch(() => ({}))) as { detail?: string; message?: string }
  if (!res.ok) {
    throw new Error(body.detail ?? 'No se pudo cambiar la contraseña')
  }
  return body.message ?? 'Contraseña actualizada.'
}

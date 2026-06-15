import { z } from 'zod'

import { USER_ROLES } from '../constants/userRoles'

const roleEnum = z.enum(USER_ROLES)

const baseFields = {
  first_name: z.string().min(1, 'Requerido').max(120, 'Máximo 120 caracteres'),
  last_name: z.string().min(1, 'Requerido').max(120, 'Máximo 120 caracteres'),
  email: z.string().min(1, 'Requerido').email('Correo inválido'),
  role: roleEnum,
  architectureAccess: z.boolean(),
}

export const adminCreateUserSchema = z
  .object({
    ...baseFields,
    password: z.string().min(8, 'Mínimo 8 caracteres').max(128, 'Máximo 128 caracteres'),
  })
  .refine((d) => d.architectureAccess, {
    message: 'Debe concederse acceso a la plataforma (módulos asignados).',
    path: ['architectureAccess'],
  })

export type AdminCreateUserForm = z.infer<typeof adminCreateUserSchema>

export const adminEditUserSchema = z
  .object({
    ...baseFields,
    password: z.string().max(128),
    isTeamLeader: z.boolean().optional(),
  })
  .refine((d) => d.architectureAccess, {
    message: 'Debe concederse acceso a la plataforma (módulos asignados).',
    path: ['architectureAccess'],
  })
  .refine((d) => d.password === '' || d.password.length >= 8, {
    message: 'Mínimo 8 caracteres si cambias la contraseña',
    path: ['password'],
  })

export type AdminEditUserForm = z.infer<typeof adminEditUserSchema>

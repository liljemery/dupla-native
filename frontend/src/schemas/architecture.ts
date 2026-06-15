import { z } from 'zod'

export const groupKindSchema = z.enum(['tirada', 'plano', 'fase'])

export const architectureItemSchema = z.object({
  id: z.string().uuid(),
  descripcion: z.string().min(1),
  capitulo: z.string().optional().nullable(),
  partida: z.string().optional().nullable(),
  unidad: z.string().optional().nullable(),
  cantidad: z.number().nonnegative().optional().nullable(),
  precio_unitario: z.number().nonnegative().optional().nullable(),
  subtotal: z.number().nonnegative().optional().nullable(),
  notas: z.string().optional().nullable(),
})

export const architectureGroupSchema = z.object({
  id: z.string().uuid(),
  kind: groupKindSchema,
  title: z.string().min(1),
  order: z.number().int().nonnegative(),
  items: z.array(architectureItemSchema),
})

export const materialRowSchema = z.object({
  id: z.string().uuid(),
  categoria: z.string().optional().nullable(),
  descripcion: z.string().min(1),
  unidad: z.string().optional().nullable(),
  cantidad_estimada: z.number().nonnegative().optional().nullable(),
  desperdicio_porcentaje: z.number().min(0).max(100).optional().nullable(),
  cantidad_total: z.number().nonnegative().optional().nullable(),
  costo_estimado: z.number().nonnegative().optional().nullable(),
  proveedor_sugerido: z.string().optional().nullable(),
})

export const architecturePayloadSchema = z.object({
  groups: z.array(architectureGroupSchema),
  materiales: z.array(materialRowSchema),
})

export type ArchitecturePayload = z.infer<typeof architecturePayloadSchema>

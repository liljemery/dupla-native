import { create } from 'zustand'

import { apiFetch } from '../api/client'
import { generateUuid } from '../lib/uuid'
import { debounce } from '../lib/debounce'
import { materialCantidadTotal } from '../lib/materialTotals'
import { architecturePayloadSchema, type ArchitecturePayload } from '../schemas/architecture'
import { useAuthStore } from './authStore'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

type MaterialRow = ArchitecturePayload['materiales'][number]

type WorkspaceState = {
  projectUuid: string | null
  data: ArchitecturePayload
  status: SaveStatus
  lastError: string | null
  lastSavedAt: string | null
  load: (projectUuid: string) => Promise<void>
  setData: (next: ArchitecturePayload) => void
  addGroup: (kind: ArchitecturePayload['groups'][number]['kind'], title: string) => void
  addItem: (groupId: string) => void
  updateItem: (
    groupId: string,
    itemId: string,
    patch: Partial<ArchitecturePayload['groups'][number]['items'][number]>,
  ) => void
  addMaterial: () => void
  updateMaterial: (materialId: string, patch: Partial<MaterialRow>) => void
  removeMaterial: (materialId: string) => void
  reset: () => void
}

const empty: ArchitecturePayload = { groups: [], materiales: [] }

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  projectUuid: null,
  data: empty,
  status: 'idle',
  lastError: null,
  lastSavedAt: null,
  reset: () =>
    set({
      projectUuid: null,
      data: empty,
      status: 'idle',
      lastError: null,
      lastSavedAt: null,
    }),
  load: async (projectUuid) => {
    const token = useAuthStore.getState().token
    if (!token) throw new Error('No session')
    const res = await apiFetch(`/api/projects/${projectUuid}/architecture`, { token })
    if (!res.ok) throw new Error('No se pudo cargar el proyecto')
    const body = (await res.json()) as {
      document: { groups?: ArchitecturePayload['groups']; materiales?: ArchitecturePayload['materiales'] }
      updated_at?: string | null
    }
    const merged: ArchitecturePayload = {
      groups: body.document.groups ?? [],
      materiales: body.document.materiales ?? [],
    }
    set({
      projectUuid,
      data: merged,
      status: 'idle',
      lastSavedAt: body.updated_at ?? null,
    })
  },
  setData: (next) => {
    set({ data: next })
    const id = get().projectUuid
    if (id) scheduleSave(id, next)
  },
  addGroup: (kind, title) => {
    const data = get().data
    const order = data.groups.length
    const next: ArchitecturePayload = {
      ...data,
      groups: [
        ...data.groups,
        {
          id: generateUuid(),
          kind,
          title,
          order,
          items: [],
        },
      ],
    }
    get().setData(next)
  },
  addItem: (groupId) => {
    const data = get().data
    const next: ArchitecturePayload = {
      ...data,
      groups: data.groups.map((g) =>
        g.id === groupId
          ? {
              ...g,
              items: [
                ...g.items,
                {
                  id: generateUuid(),
                  descripcion: 'Nuevo ítem',
                  cantidad: 0,
                  precio_unitario: 0,
                  subtotal: 0,
                },
              ],
            }
          : g,
      ),
    }
    get().setData(next)
  },
  updateItem: (groupId, itemId, patch) => {
    const data = get().data
    const next: ArchitecturePayload = {
      ...data,
      groups: data.groups.map((g) =>
        g.id === groupId
          ? {
              ...g,
              items: g.items.map((it) => {
                if (it.id !== itemId) return it
                const merged = { ...it, ...patch }
                const c = Number(merged.cantidad ?? 0)
                const p = Number(merged.precio_unitario ?? 0)
                merged.subtotal = Math.round(c * p * 100) / 100
                return merged
              }),
            }
          : g,
      ),
    }
    get().setData(next)
  },
  addMaterial: () => {
    const data = get().data
    const row: MaterialRow = {
      id: generateUuid(),
      descripcion: 'Nuevo material',
      cantidad_estimada: 0,
      desperdicio_porcentaje: 0,
      cantidad_total: materialCantidadTotal(0, 0),
    }
    const next: ArchitecturePayload = {
      ...data,
      materiales: [...data.materiales, row],
    }
    get().setData(next)
  },
  updateMaterial: (materialId, patch) => {
    const data = get().data
    const next: ArchitecturePayload = {
      ...data,
      materiales: data.materiales.map((m) => {
        if (m.id !== materialId) return m
        const merged: MaterialRow = { ...m, ...patch }
        merged.cantidad_total = materialCantidadTotal(
          merged.cantidad_estimada,
          merged.desperdicio_porcentaje,
        )
        return merged
      }),
    }
    get().setData(next)
  },
  removeMaterial: (materialId) => {
    const data = get().data
    const next: ArchitecturePayload = {
      ...data,
      materiales: data.materiales.filter((m) => m.id !== materialId),
    }
    get().setData(next)
  },
}))

const scheduleSave = debounce(async (projectUuid: string, payload: ArchitecturePayload) => {
  const token = useAuthStore.getState().token
  if (!token) return
  const parsed = architecturePayloadSchema.safeParse(payload)
  if (!parsed.success) {
    useWorkspaceStore.setState({ status: 'error', lastError: 'Validación local fallida' })
    return
  }
  useWorkspaceStore.setState({ status: 'saving', lastError: null })
  const res = await apiFetch(`/api/projects/${projectUuid}/architecture`, {
    method: 'PUT',
    token,
    body: JSON.stringify(parsed.data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    useWorkspaceStore.setState({
      status: 'error',
      lastError: String((err as { detail?: unknown }).detail ?? res.statusText),
    })
    return
  }
  useWorkspaceStore.setState({ status: 'saved', lastSavedAt: new Date().toISOString() })
}, 900)

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import { apiFetch } from '../api/client'
import type { UserRole } from '../constants/userRoles'
import { hasPermission } from '../lib/accessPermissions'
import { invalidateAdminUsersDirectoryCache } from '../lib/adminUsersDirectoryCache'
import { AUTH_PERSIST_KEY } from './authConstants'

type Role = UserRole

export type WorkspaceOption = {
  uuid: string
  name: string
  is_default?: boolean
}

export type MeProfile = {
  uuid: string
  email: string
  first_name: string
  last_name: string
  role: Role
  role_uuids?: string[]
  role_slugs?: string[]
  role_names?: string[]
  permissions?: string[]
  must_change_password?: boolean
  active_workspace_uuid?: string | null
  active_workspace_name?: string | null
  available_workspaces?: WorkspaceOption[]
}

type AuthState = {
  token: string | null
  email: string | null
  firstName: string | null
  lastName: string | null
  role: Role | null
  roleUuids: string[]
  roleSlugs: string[]
  permissions: string[]
  userUuid: string | null
  mustChangePassword: boolean
  activeWorkspaceUuid: string | null
  activeWorkspaceName: string | null
  availableWorkspaces: WorkspaceOption[]
  hasPermission: (key: string) => boolean
  setSession: (
    token: string,
    email: string,
    role: Role,
    userUuid: string,
    firstName: string,
    lastName: string,
    mustChangePassword?: boolean,
    permissions?: string[],
    workspace?: {
      activeWorkspaceUuid?: string | null
      activeWorkspaceName?: string | null
      availableWorkspaces?: WorkspaceOption[]
    },
  ) => void
  applyProfile: (profile: MeProfile, token?: string) => void
  refreshProfile: () => Promise<void>
  clearMustChangePassword: () => void
  logout: () => void
  login: (email: string, password: string) => Promise<boolean>
}

function workspaceFromProfile(profile: MeProfile): {
  activeWorkspaceUuid: string | null
  activeWorkspaceName: string | null
  availableWorkspaces: WorkspaceOption[]
} {
  const available = (profile.available_workspaces ?? []).map((w) => ({
    uuid: w.uuid,
    name: w.name,
    is_default: w.is_default,
  }))
  return {
    activeWorkspaceUuid: profile.active_workspace_uuid ?? null,
    activeWorkspaceName: profile.active_workspace_name ?? null,
    availableWorkspaces: available,
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      email: null,
      firstName: null,
      lastName: null,
      role: null,
      roleUuids: [],
      roleSlugs: [],
      permissions: [],
      userUuid: null,
      mustChangePassword: false,
      activeWorkspaceUuid: null,
      activeWorkspaceName: null,
      availableWorkspaces: [],
      hasPermission: (key) => hasPermission(get().permissions, key),
      setSession: (
        token,
        email,
        role,
        userUuid,
        firstName,
        lastName,
        mustChangePassword = false,
        permissions = [],
        workspace,
      ) =>
        set({
          token,
          email,
          role,
          userUuid,
          firstName,
          lastName,
          mustChangePassword,
          permissions,
          roleSlugs: [],
          roleUuids: [],
          activeWorkspaceUuid: workspace?.activeWorkspaceUuid ?? null,
          activeWorkspaceName: workspace?.activeWorkspaceName ?? null,
          availableWorkspaces: workspace?.availableWorkspaces ?? [],
        }),
      applyProfile: (profile, token) => {
        const ws = workspaceFromProfile(profile)
        set({
          token: token ?? get().token,
          email: profile.email,
          firstName: profile.first_name,
          lastName: profile.last_name,
          role: profile.role,
          userUuid: profile.uuid,
          mustChangePassword: profile.must_change_password ?? get().mustChangePassword,
          permissions: profile.permissions ?? [],
          roleUuids: profile.role_uuids ?? [],
          roleSlugs: profile.role_slugs ?? [],
          ...ws,
        })
      },
      refreshProfile: async () => {
        const token = get().token
        if (!token) return
        const res = await apiFetch('/api/me', { token })
        if (!res.ok) return
        const profile = (await res.json()) as MeProfile
        get().applyProfile(profile, token)
        invalidateAdminUsersDirectoryCache()
      },
      clearMustChangePassword: () => set({ mustChangePassword: false }),
      logout: () =>
        set({
          token: null,
          email: null,
          firstName: null,
          lastName: null,
          role: null,
          roleUuids: [],
          roleSlugs: [],
          permissions: [],
          userUuid: null,
          mustChangePassword: false,
          activeWorkspaceUuid: null,
          activeWorkspaceName: null,
          availableWorkspaces: [],
        }),
      login: async (email, password) => {
        const body = new URLSearchParams()
        body.set('username', email)
        body.set('password', password)
        const res = await apiFetch('/api/auth/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: body.toString(),
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({}))
          throw new Error((err as { detail?: string }).detail ?? 'Login failed')
        }
        const data = (await res.json()) as { access_token: string; must_change_password?: boolean }
        const me = await apiFetch('/api/me', { token: data.access_token })
        if (!me.ok) throw new Error('Failed to load profile')
        const profile = (await me.json()) as MeProfile
        const mustChangePassword = profile.must_change_password ?? data.must_change_password ?? false
        const ws = workspaceFromProfile(profile)
        set({
          token: data.access_token,
          email: profile.email,
          firstName: profile.first_name,
          lastName: profile.last_name,
          role: profile.role,
          userUuid: profile.uuid,
          mustChangePassword,
          permissions: profile.permissions ?? [],
          roleUuids: profile.role_uuids ?? [],
          roleSlugs: profile.role_slugs ?? [],
          ...ws,
        })
        return mustChangePassword
      },
    }),
    { name: AUTH_PERSIST_KEY },
  ),
)

import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import {
  BarChart3,
  BookOpen,
  GitBranch,
  ChevronLeft,
  ChevronRight,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  MessageCircle,
  UserRound,
  Users,
} from 'lucide-react'

import { apiFetch } from '../api/client'
import { DuplaSidebarLogo } from './DuplaSidebarLogo'
import { hasElevatedAccess } from '../lib/accessPermissions'
import { useAuthStore } from '../store/authStore'
import { useChatStore } from '../store/chatStore'

const STORAGE_KEY = 'dupla-sidebar-collapsed'

function readStoredCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function Sidebar() {
  const email = useAuthStore((s) => s.email)
  const role = useAuthStore((s) => s.role)
  const isTeamLeader = useAuthStore((s) => s.isTeamLeader)
  const elevated = hasElevatedAccess(role, isTeamLeader)
  const token = useAuthStore((s) => s.token)
  const logout = useAuthStore((s) => s.logout)
  const hasUnread = useChatStore((s) => s.hasUnread)
  const [collapsed, setCollapsed] = useState(readStoredCollapsed)
  const [unreadNotifs, setUnreadNotifs] = useState(0)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0')
    } catch {
      /* ignore */
    }
  }, [collapsed])

  useEffect(() => {
    if (!token) return
    let cancelled = false
    void (async () => {
      const res = await apiFetch('/api/me/notifications?unread_only=true', { token })
      if (!res.ok || cancelled) return
      const rows = (await res.json()) as unknown[]
      if (!cancelled) setUnreadNotifs(rows.length)
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  const linkBase =
    'flex items-center rounded-xl text-base font-medium text-ink outline-none transition-colors duration-150 hover:bg-black/5 active:bg-black/10 focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-elevated'
  const linkExpanded = 'justify-between gap-2 px-3.5 py-2.5'
  const linkCollapsed = 'justify-center px-2.5 py-3'
  const activeClass = 'bg-primary/10 text-primary ring-1 ring-primary/20'

  const userTooltip = [email, role, unreadNotifs > 0 ? `${unreadNotifs} aviso(s)` : null]
    .filter(Boolean)
    .join(' · ')

  return (
    <aside
      data-tour="sidebar-root"
      className={`flex h-full min-h-0 max-h-full shrink-0 flex-col overflow-hidden border-r border-slate-200/80 bg-white transition-[width] duration-200 ease-out ${
        collapsed ? 'w-[4.5rem]' : 'w-56 md:w-60'
      }`}
    >
      <div
        className={`flex shrink-0 border-b border-black/10 ${
          collapsed ? 'items-center justify-center px-2.5 py-4 md:py-5' : 'px-4 py-5 md:px-5 md:py-7'
        }`}
      >
        <div className={collapsed ? 'flex justify-center' : 'flex flex-col gap-1'}>
          <DuplaSidebarLogo
            className={
              collapsed
                ? 'mx-auto h-9 w-9 object-contain'
                : 'h-10 w-auto max-w-[min(100%,320px)] object-contain object-left md:h-11'
            }
          />
        </div>
      </div>
      <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto overflow-x-hidden p-2.5" aria-label="Principal">
        <NavLink
          data-tour="sidebar-projects"
          to="/app/projects"
          title="Proyectos"
          end
          className={({ isActive }) =>
            `${linkBase} ${collapsed ? linkCollapsed : linkExpanded} ${isActive ? activeClass : ''}`
          }
        >
          <FolderKanban className="h-5 w-5 shrink-0" aria-hidden />
          <span className={collapsed ? 'sr-only' : 'min-w-0 flex-1'}>Proyectos</span>
        </NavLink>
        {elevated ? (
          <NavLink
            to="/app/flows"
            title="Flujos"
            className={({ isActive }) =>
              `${linkBase} ${collapsed ? linkCollapsed : linkExpanded} ${isActive ? activeClass : ''}`
            }
          >
            <GitBranch className="h-5 w-5 shrink-0" aria-hidden />
            <span className={collapsed ? 'sr-only' : 'min-w-0 flex-1'}>Flujos</span>
          </NavLink>
        ) : null}
        <NavLink
          data-tour="sidebar-chat"
          to="/app/chat"
          title="Chat interno"
          className={({ isActive }) =>
            `${linkBase} ${collapsed ? linkCollapsed : `${linkExpanded} gap-2`} ${isActive ? activeClass : ''}`
          }
        >
          <span className="relative shrink-0">
            <MessageCircle className="h-5 w-5" aria-hidden />
            {hasUnread && collapsed ? (
              <span
                className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-primary ring-2 ring-white"
                aria-hidden
              />
            ) : null}
          </span>
          <span className={`min-w-0 flex-1 ${collapsed ? 'sr-only' : ''}`}>Chat interno</span>
          {!collapsed && hasUnread ? (
            <span className="h-2 w-2 shrink-0 rounded-full bg-primary" aria-label="Mensajes nuevos" />
          ) : null}
        </NavLink>
        <NavLink
          data-tour="sidebar-tasks"
          to="/app/tasks"
          title="Tablero"
          className={({ isActive }) =>
            `${linkBase} ${collapsed ? linkCollapsed : linkExpanded} ${isActive ? activeClass : ''}`
          }
        >
          <LayoutDashboard className="h-5 w-5 shrink-0" aria-hidden />
          <span className={collapsed ? 'sr-only' : 'min-w-0 flex-1'}>Tablero</span>
        </NavLink>
        <NavLink
          data-tour="sidebar-tutoriales"
          to="/app/tutoriales"
          title="Tutoriales"
          className={({ isActive }) =>
            `${linkBase} ${collapsed ? linkCollapsed : linkExpanded} ${isActive ? activeClass : ''}`
          }
        >
          <BookOpen className="h-5 w-5 shrink-0" aria-hidden />
          <span className={collapsed ? 'sr-only' : 'min-w-0 flex-1'}>Tutoriales</span>
        </NavLink>
        {elevated ? (
          <>
            <NavLink
              data-tour="sidebar-dashboard"
              to="/app/dashboard"
              title="Panel gerencial"
              className={({ isActive }) =>
                `${linkBase} ${collapsed ? linkCollapsed : linkExpanded} ${isActive ? activeClass : ''}`
              }
            >
              <BarChart3 className="h-5 w-5 shrink-0" aria-hidden />
              <span className={collapsed ? 'sr-only' : 'min-w-0 flex-1'}>Panel</span>
            </NavLink>
            <NavLink
              data-tour="sidebar-admin"
              to="/app/admin"
              title="Usuarios"
              className={({ isActive }) =>
                `${linkBase} ${collapsed ? linkCollapsed : linkExpanded} ${isActive ? activeClass : ''}`
              }
            >
              <Users className="h-5 w-5 shrink-0" aria-hidden />
              <span className={collapsed ? 'sr-only' : 'min-w-0 flex-1'}>Usuarios</span>
            </NavLink>
          </>
        ) : null}
      </nav>

      <div className="border-t border-black/10">
        {collapsed ? (
          <div className="flex flex-col items-center gap-2.5 p-2.5">
            <span className="relative" title={userTooltip}>
              <UserRound className="h-6 w-6 text-muted" aria-hidden />
              {unreadNotifs > 0 ? (
                <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary/20 px-0.5 text-[10px] font-bold text-primary">
                  {unreadNotifs > 9 ? '9+' : unreadNotifs}
                </span>
              ) : null}
            </span>
            <button
              type="button"
              title="Salir"
              className="rounded-md p-2 text-muted outline-none transition hover:bg-black/5 hover:text-ink focus-visible:ring-2 focus-visible:ring-primary/30"
              onClick={() => logout()}
            >
              <LogOut className="h-5 w-5" aria-hidden />
              <span className="sr-only">Salir</span>
            </button>
          </div>
        ) : (
          <div className="space-y-2.5 px-3.5 py-4">
            <p className="break-all text-sm font-medium leading-snug text-ink">{email}</p>
            {role ? <p className="text-xs text-muted">{role}</p> : null}
            {unreadNotifs > 0 ? (
              <span className="inline-flex rounded-full bg-primary/15 px-2.5 py-0.5 text-xs font-medium text-primary">
                {unreadNotifs} aviso{unreadNotifs === 1 ? '' : 's'}
              </span>
            ) : null}
            <button
              type="button"
              className="flex w-full items-center justify-center gap-2 rounded-md border border-black/12 py-2.5 text-sm font-medium text-muted transition hover:bg-black/[0.04] hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              onClick={() => logout()}
            >
              <LogOut className="h-3.5 w-3.5 shrink-0" aria-hidden />
              Salir
            </button>
            <NavLink
              to="/app/settings"
              className="flex w-full items-center justify-center gap-2 rounded-md border border-black/12 py-2.5 text-sm font-medium text-muted transition hover:bg-black/[0.04] hover:text-ink"
            >
              Configuración
            </NavLink>
          </div>
        )}
      </div>

      <div className="border-t border-black/10 p-2.5" data-tour="sidebar-collapse">
        <button
          type="button"
          className="flex w-full items-center justify-center gap-2 rounded-md border border-black/10 bg-white px-2.5 py-2.5 text-muted outline-none transition hover:bg-black/[0.04] hover:text-ink focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2"
          aria-expanded={!collapsed}
          aria-label={collapsed ? 'Expandir menú lateral' : 'Contraer menú lateral'}
          onClick={() => setCollapsed((c) => !c)}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4 shrink-0" aria-hidden />
          ) : (
            <>
              <ChevronLeft className="h-4 w-4 shrink-0" aria-hidden />
              <span className="text-sm font-medium">Contraer</span>
            </>
          )}
        </button>
      </div>
    </aside>
  )
}

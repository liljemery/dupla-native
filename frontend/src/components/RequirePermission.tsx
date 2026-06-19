import { Navigate, Outlet } from 'react-router-dom'

import { useAuthStore } from '../store/authStore'

type Props = {
  permission: string
  fallback?: string
}

export function RequirePermission({ permission, fallback = '/app/projects' }: Props) {
  const has = useAuthStore((s) => s.hasPermission)
  if (!has(permission)) return <Navigate to={fallback} replace />
  return <Outlet />
}

import { Navigate, Outlet, Route, Routes } from 'react-router-dom'

import { MainLayout } from './components/MainLayout'
import { AdminUsersPage } from './pages/AdminUsersPage'
import { ChatPage } from './pages/ChatPage'
import { ChangePasswordPage } from './pages/ChangePasswordPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { LoginPage } from './pages/LoginPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { ProjectWorkspacePage } from './pages/ProjectWorkspacePage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { SettingsPage } from './pages/SettingsPage'
import { DashboardPage } from './pages/DashboardPage'
import { TaskboardPage } from './pages/TaskboardPage'
import { TutorialesPage } from './pages/TutorialesPage'
import { FlowsHubPage } from './pages/FlowsHubPage'
import { FlowBoardPage } from './pages/FlowBoardPage'
import { hasElevatedAccess } from './lib/accessPermissions'
import { useAuthStore } from './store/authStore'

function RequireAuth() {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <Outlet />
}

function RequirePasswordChanged() {
  const mustChangePassword = useAuthStore((s) => s.mustChangePassword)
  if (mustChangePassword) return <Navigate to="/change-password" replace />
  return <Outlet />
}

function RequireElevatedAccess() {
  const role = useAuthStore((s) => s.role)
  const isTeamLeader = useAuthStore((s) => s.isTeamLeader)
  if (!hasElevatedAccess(role, isTeamLeader)) return <Navigate to="/app/projects" replace />
  return <Outlet />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/app/projects" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/change-password" element={<ChangePasswordPage />} />
        <Route element={<RequirePasswordChanged />}>
          <Route element={<MainLayout />}>
            <Route path="/app/projects" element={<ProjectsPage />} />
            <Route path="/app/projects/:projectUuid" element={<ProjectWorkspacePage />} />
            <Route path="/app/chat" element={<ChatPage />} />
            <Route path="/app/tasks" element={<TaskboardPage />} />
            <Route path="/app/settings" element={<SettingsPage />} />
            <Route path="/app/tutoriales" element={<TutorialesPage />} />
            <Route element={<RequireElevatedAccess />}>
              <Route path="/app/admin" element={<AdminUsersPage />} />
              <Route path="/app/dashboard" element={<DashboardPage />} />
              <Route path="/app/flows" element={<FlowsHubPage />} />
              <Route path="/app/flows/:flowUuid" element={<FlowBoardPage />} />
            </Route>
          </Route>
        </Route>
      </Route>
      <Route path="/app" element={<Navigate to="/app/projects" replace />} />
      <Route path="*" element={<Navigate to="/app/projects" replace />} />
    </Routes>
  )
}

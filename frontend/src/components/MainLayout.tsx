import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'

import { apiFetch } from '../api/client'
import { useChatSync } from '../hooks/useChatSync'
import { useAuthStore, type MeProfile } from '../store/authStore'
import { DuplaAssistantChat } from './DuplaAssistantChat'
import { Sidebar } from './Sidebar'

export function MainLayout() {
  useChatSync()
  const token = useAuthStore((s) => s.token)
  const userUuid = useAuthStore((s) => s.userUuid)
  const applyProfile = useAuthStore((s) => s.applyProfile)

  useEffect(() => {
    if (!token || userUuid) return
    void (async () => {
      const res = await apiFetch('/api/me', { token })
      if (!res.ok) return
      const p = (await res.json()) as MeProfile
      applyProfile(p, token)
    })()
  }, [token, userUuid, applyProfile])

  return (
    <div className="flex h-dvh min-h-0 overflow-hidden bg-surface-page text-ink">
      <DuplaAssistantChat />
      <Sidebar />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[url('/engineering-bg.png')] bg-cover bg-fixed bg-center">
        <main className="mx-auto flex min-h-0 w-full max-w-[min(100%,88rem)] flex-1 flex-col overflow-hidden px-4 py-4 sm:px-6 sm:py-5 md:px-8 md:py-6">
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden scroll-smooth [-webkit-overflow-scrolling:touch]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import { DEFAULT_DISPLAY_NAME } from '../constants/app'
import { AppSidebar } from './ui/AppSidebar'

export const AppLayout = () => {
  const [displayName, setDisplayName] = useState(DEFAULT_DISPLAY_NAME)
  const location = useLocation()
  const isChatRoute = location.pathname.startsWith('/chat')

  useEffect(() => {
    const load = async () => {
      try {
        const settings = await api.getSettings()
        if (settings.display_name) {
          setDisplayName(settings.display_name)
        }
      } catch {
        // optional on first boot
      }
    }
    void load()
  }, [])

  return (
    <div className="relative flex h-screen w-screen overflow-hidden bg-white text-slate-900">
      {/* Ambient background */}
      <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-white" aria-hidden>
        <div className="absolute -left-32 top-0 h-96 w-96 rounded-full bg-blue-100/60 blur-3xl animate-float" />
        <div className="absolute -right-32 top-1/4 h-80 w-80 rounded-full bg-cyan-100/50 blur-3xl animate-float-delayed" />
        <div className="absolute bottom-0 left-1/3 h-64 w-64 rounded-full bg-sky-50/80 blur-3xl" />
        <div
          className="absolute inset-0 opacity-[0.35]"
          style={{
            backgroundImage: 'radial-gradient(circle at 1px 1px, rgb(229 231 235) 1px, transparent 0)',
            backgroundSize: '32px 32px',
          }}
        />
      </div>

      {/* Main Collapsible App Sidebar */}
      <AppSidebar displayName={displayName} />

      {/* Main Application Area */}
      <main className="flex-1 flex flex-col h-full overflow-hidden min-w-0">
        <div
          className={`flex-1 h-full min-w-0 ${
            isChatRoute
              ? 'p-0 overflow-hidden'
              : 'overflow-y-auto px-4 py-8 md:px-8 max-w-7xl mx-auto w-full'
          }`}
        >
          <Outlet context={{ displayName, setDisplayName }} />
        </div>
      </main>
    </div>
  )
}

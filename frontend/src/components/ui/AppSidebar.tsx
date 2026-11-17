import { useEffect, useRef, useState } from 'react'
import {
  ChevronDown,
  CircleHelp,
  BookOpen,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Mic,
  PanelLeftClose,
  Plus,
  Search,
  Settings,
  Sparkles,
  User,
  Trash2,
  Edit3,
  Check,
  X,
} from 'lucide-react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useUser, type UserRole } from '../../context/UserContext'
import { useAuth } from '../../context/AuthContext'
import { useChat } from '../../context/ChatContext'
import { useSidebar } from '../../context/SidebarContext'
import type { ChatConversation } from '../../features/chat/hooks/useChatPersistence'

interface AppSidebarProps {
  displayName: string
  version?: string | null
}

const roleLabels: Record<UserRole, string> = {
  admin: 'Administrador',
  pm: 'Project Manager',
  funcional: 'Analista Funcional',
  qa: 'Tester',
}

function getInitials(nameStr: string): string {
  const parts = nameStr.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return 'AS'
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export const AppSidebar = ({ displayName, version }: AppSidebarProps) => {
  const { isCollapsed, toggleSidebar } = useSidebar()
  const [chatExpanded, setChatExpanded] = useState(true)
  const [knowledgeExpanded, setKnowledgeExpanded] = useState(false)
  const [profileMenuOpen, setProfileMenuOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')

  const profileRef = useRef<HTMLDivElement>(null)
  const location = useLocation()
  const navigate = useNavigate()
  const { user } = useUser()
  const { logout } = useAuth()

  const activeName = user?.display_name || displayName
  const userRole = (user?.user_role as UserRole) || 'admin'
  const roleLabel = roleLabels[userRole] || 'Administrador'
  const initials = getInitials(activeName)

  const {
    conversations,
    activeConversationId,
    createConversation,
    renameConversation,
    deleteConversation,
    switchConversation,
    searchQuery,
    setSearchQuery,
  } = useChat()

  const isChatActive = location.pathname.startsWith('/chat')
  const isKnowledgeActive = location.pathname.startsWith('/knowledge')
  const isTranscriptionActive = location.pathname.startsWith('/transcripciones')

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const filteredConversations = conversations.filter((c) =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase()),
  )

  const handleCreateNewChat = () => {
    createConversation('Nueva conversación')
    if (!isChatActive) {
      navigate('/chat')
    }
  }

  const handleSelectChat = (id: string) => {
    switchConversation(id)
    if (!isChatActive) {
      navigate(`/chat?session=${id}`)
    }
  }

  const startEditing = (conv: ChatConversation) => {
    setEditingId(conv.id)
    setEditValue(conv.name)
  }

  const confirmEdit = (id: string) => {
    if (editValue.trim()) {
      renameConversation(id, editValue.trim())
    }
    setEditingId(null)
    setEditValue('')
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditValue('')
  }

  const navItemClass = (isActive: boolean) =>
    `flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-all duration-200 ${isActive
      ? 'bg-blue-50 text-[#002777] shadow-xs ring-1 ring-blue-200 font-semibold'
      : 'text-slate-600 hover:bg-slate-100/80 hover:text-slate-900'
    } ${isCollapsed ? 'justify-center px-0' : ''}`

  return (
    <aside
      className={`relative flex flex-col shrink-0 border-r border-slate-200 bg-white/95 backdrop-blur-xl transition-all duration-300 z-30 select-none ${isCollapsed ? 'w-16' : 'w-64'
        }`}
    >
      {/* Decorative Brand Gradient Accent Line on Top */}
      <div
        className="h-0.5 w-full bg-gradient-to-r from-[#002777] via-[#004497] to-cyan-400"
        aria-hidden
      />

      {/* Top Header / Logo + Version */}
      <div
        className={`flex items-center border-b border-slate-100 shrink-0 py-3 ${isCollapsed ? 'justify-center px-2' : 'justify-between px-3.5'
          }`}
      >
        <NavLink
          to="/"
          className="flex items-center gap-2.5 overflow-visible transition-all"
          title="FuncAssist"
        >
          <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#002777] to-[#004497] text-white shadow-md shadow-[#002777]/30 ring-1 ring-blue-100 overflow-visible">
            <Sparkles className="h-4 w-4" aria-hidden />
            <span
              className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-cyan-400 ring-2 ring-white animate-pulse-soft z-10"
              aria-hidden
            />
          </div>
          {!isCollapsed && (
            <div className="flex items-baseline gap-1.5 overflow-hidden">
              <span className="text-sm font-bold tracking-tight text-slate-900 whitespace-nowrap">
                Func<span className="font-normal text-blue-700">Assist</span>
              </span>
              {version && (
                <span className="text-xs text-slate-500 font-normal font-mono whitespace-nowrap">
                  v.{version}
                </span>
              )}
            </div>
          )}
        </NavLink>

        {/* Botón de alternar colapso en el header (solo visible cuando está expandido) */}
        {!isCollapsed && (
          <button
            type="button"
            onClick={toggleSidebar}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition cursor-pointer shrink-0"
            title="Colapsar barra lateral"
            aria-label="Colapsar barra lateral"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-1 scrollbar-thin">
        {/* Inicio */}
        <NavLink to="/" end className={({ isActive }) => navItemClass(isActive)} title="Inicio">
          <LayoutDashboard className="h-4 w-4 shrink-0 opacity-70" />
          {!isCollapsed && <span>Inicio</span>}
        </NavLink>

        {/* Chat Section */}
        <div>
          <div
            className={`flex items-center justify-between rounded-xl px-3 py-2 text-sm font-medium transition-all duration-200 cursor-pointer ${isChatActive
                ? 'bg-blue-50 text-[#002777] shadow-xs ring-1 ring-blue-200 font-semibold'
                : 'text-slate-600 hover:bg-slate-100/80 hover:text-slate-900'
              } ${isCollapsed ? 'justify-center px-0' : ''}`}
            onClick={() => {
              if (isCollapsed) {
                toggleSidebar()
                setChatExpanded(true)
                navigate('/chat')
              } else {
                setChatExpanded(!chatExpanded)
              }
            }}
            title="Chat"
          >
            <div className="flex items-center gap-3 min-w-0">
              <MessageSquare className="h-4 w-4 shrink-0 opacity-70" />
              {!isCollapsed && <span>Chat</span>}
            </div>

            {!isCollapsed && (
              <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  onClick={handleCreateNewChat}
                  className="p-1 rounded-md text-[#002777] hover:bg-blue-100/80 transition cursor-pointer"
                  title="Nuevo chat"
                  aria-label="Nuevo chat"
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => setChatExpanded(!chatExpanded)}
                  className="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition cursor-pointer"
                  title={chatExpanded ? 'Plegar chats' : 'Desplegar chats'}
                >
                  <ChevronDown
                    className={`h-3.5 w-3.5 transition-transform duration-200 ${chatExpanded ? 'rotate-180' : ''
                      }`}
                  />
                </button>
              </div>
            )}
          </div>

          {/* Expanded Chat Sub-tree */}
          {!isCollapsed && chatExpanded && (
            <div className="mt-2 pl-2 pr-1 space-y-2">
              {/* Search Bar */}
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400 pointer-events-none" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Buscar chats..."
                  className="w-full text-xs pl-8 pr-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-800 placeholder-slate-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-[#002777] focus:border-blue-300 transition"
                />
              </div>

              {/* Single Recientes Header */}
              <div className="px-1 pt-1">
                <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                  Recientes
                </p>
              </div>

              {/* Conversations List */}
              <div className="space-y-0.5 max-h-56 overflow-y-auto scrollbar-thin">
                {filteredConversations.length === 0 ? (
                  <p className="px-2 py-3 text-[11px] text-slate-400 italic text-center">
                    {conversations.length === 0 ? 'Sin conversaciones' : 'Sin coincidencias'}
                  </p>
                ) : (
                  filteredConversations.map((conv) => {
                    const isSelected = isChatActive && conv.id === activeConversationId
                    const isEditing = editingId === conv.id

                    return (
                      <div
                        key={conv.id}
                        className={`group relative flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs transition-colors cursor-pointer ${isSelected
                            ? 'bg-blue-100/70 text-[#002777] font-semibold'
                            : 'text-slate-700 hover:bg-slate-100 hover:text-slate-900'
                          }`}
                        onClick={() => !isEditing && handleSelectChat(conv.id)}
                      >
                        {isEditing ? (
                          <div
                            className="flex items-center gap-1 w-full"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <input
                              type="text"
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') confirmEdit(conv.id)
                                if (e.key === 'Escape') cancelEdit()
                              }}
                              autoFocus
                              className="flex-1 text-xs px-1.5 py-0.5 bg-white text-slate-900 border border-[#002777] rounded focus:outline-none"
                            />
                            <button
                              type="button"
                              onClick={() => confirmEdit(conv.id)}
                              className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"
                              title="Guardar"
                            >
                              <Check className="h-3 w-3" />
                            </button>
                            <button
                              type="button"
                              onClick={cancelEdit}
                              className="p-1 text-slate-400 hover:bg-slate-100 rounded"
                              title="Cancelar"
                            >
                              <X className="h-3 w-3" />
                            </button>
                          </div>
                        ) : (
                          <>
                            <div className="flex items-center gap-2 min-w-0 flex-1">
                              <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-50 text-[#002777]" />
                              <span className="truncate" title={conv.name}>
                                {conv.name}
                              </span>
                            </div>

                            <div
                              className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 ml-1"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <button
                                type="button"
                                onClick={() => startEditing(conv)}
                                className="p-1 text-slate-400 hover:text-amber-600 rounded transition"
                                title="Renombrar chat"
                              >
                                <Edit3 className="h-3 w-3" />
                              </button>
                              <button
                                type="button"
                                onClick={() => deleteConversation(conv.id)}
                                className="p-1 text-slate-400 hover:text-red-600 rounded transition"
                                title="Eliminar chat"
                              >
                                <Trash2 className="h-3 w-3" />
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          )}
        </div>

        {/* Transcripciones */}
        <NavLink
          to="/transcripciones"
          className={({ isActive }) => navItemClass(isActive || isTranscriptionActive)}
          title="Transcripciones"
        >
          <Mic className="h-4 w-4 shrink-0 opacity-70" />
          {!isCollapsed && <span>Transcripciones</span>}
        </NavLink>

        {/* Conocimiento (Biblioteca + Consultar Producto) */}
        <div>
          <button
            type="button"
            onClick={() => {
              if (isCollapsed) {
                toggleSidebar()
                setKnowledgeExpanded(true)
              } else {
                setKnowledgeExpanded(!knowledgeExpanded)
              }
            }}
            className={`w-full flex items-center justify-between rounded-xl px-3 py-2 text-sm font-medium transition-all duration-200 cursor-pointer ${isKnowledgeActive
                ? 'bg-blue-50 text-[#002777] shadow-xs ring-1 ring-blue-200 font-semibold'
                : 'text-slate-600 hover:bg-slate-100/80 hover:text-slate-900'
              } ${isCollapsed ? 'justify-center px-0' : ''}`}
            title="Conocimiento"
          >
            <div className="flex items-center gap-3">
              <BookOpen className="h-4 w-4 shrink-0 opacity-70" />
              {!isCollapsed && <span>Conocimiento</span>}
            </div>
            {!isCollapsed && (
              <ChevronDown
                className={`h-3.5 w-3.5 text-slate-400 transition-transform duration-200 ${knowledgeExpanded ? 'rotate-180' : ''
                  }`}
              />
            )}
          </button>

          {!isCollapsed && knowledgeExpanded && (
            <div className="mt-1 pl-6 space-y-0.5">
              <NavLink
                to="/knowledge"
                end
                className={({ isActive }) =>
                  `flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs transition-colors ${isActive
                    ? 'bg-blue-50 text-[#002777] font-semibold'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`
                }
              >
                <BookOpen className="h-3.5 w-3.5 shrink-0 opacity-60" />
                <span>Biblioteca</span>
              </NavLink>
              <NavLink
                to="/knowledge/ask"
                className={({ isActive }) =>
                  `flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs transition-colors ${isActive
                    ? 'bg-blue-50 text-[#002777] font-semibold'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`
                }
              >
                <CircleHelp className="h-3.5 w-3.5 shrink-0 opacity-60" />
                <span>Consultar Producto</span>
              </NavLink>
            </div>
          )}
        </div>

        {/* Configuraciones */}
        <NavLink
          to="/settings"
          className={({ isActive }) => navItemClass(isActive)}
          title="Configuraciones"
        >
          <Settings className="h-4 w-4 shrink-0 opacity-70" />
          {!isCollapsed && <span>Configuraciones</span>}
        </NavLink>
      </nav>

      {/* Footer Profile Section with Popover */}
      <div className="relative p-2.5 border-t border-slate-100 shrink-0" ref={profileRef}>
        {profileMenuOpen && (
          <div className="absolute left-3 bottom-16 w-56 rounded-2xl bg-white border border-slate-200 p-2 text-slate-800 shadow-xl z-50 animate-fadeIn">
            {/* Header info */}
            <div className="flex items-center gap-2.5 p-2 rounded-xl bg-slate-50 border border-slate-100">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#002777] to-[#004497] text-white font-extrabold text-xs shadow-md shadow-[#002777]/20">
                {initials}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-bold text-slate-900 truncate" title={activeName}>
                  {activeName}
                </p>
                <p className="text-[11px] font-semibold text-blue-700 truncate" title={roleLabel}>
                  {roleLabel}
                </p>
              </div>
            </div>

            <div className="border-t border-slate-100 my-1.5" />

            <div className="space-y-0.5">
              <NavLink
                to="/profile"
                onClick={() => setProfileMenuOpen(false)}
                className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-slate-700 hover:bg-slate-100 hover:text-slate-900 transition"
              >
                <User className="h-3.5 w-3.5 text-slate-500" />
                <span>Perfil</span>
              </NavLink>

              <button
                type="button"
                onClick={() => {
                  setProfileMenuOpen(false)
                  logout()
                }}
                className="flex w-full items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-red-600 hover:bg-red-50 hover:text-red-700 transition cursor-pointer"
              >
                <LogOut className="h-3.5 w-3.5 text-red-500" />
                <span>Cerrar sesión</span>
              </button>
            </div>
          </div>
        )}

        {/* Profile Card Trigger */}
        <div
          onClick={() => setProfileMenuOpen(!profileMenuOpen)}
          className={`flex items-center justify-between gap-2.5 p-2 rounded-xl hover:bg-slate-100/80 transition cursor-pointer ${isCollapsed ? 'justify-center px-0' : ''
            }`}
          title={`${activeName} (${roleLabel})`}
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#002777] to-[#004497] text-white font-extrabold text-xs shadow-md shadow-[#002777]/20 ring-2 ring-blue-100">
              {initials}
            </div>
            {!isCollapsed && (
              <div className="min-w-0 flex-1">
                <p className="text-xs font-bold text-slate-900 truncate" title={activeName}>
                  {activeName}
                </p>
                <p className="text-[11px] font-semibold text-blue-700 truncate" title={roleLabel}>
                  {roleLabel}
                </p>
              </div>
            )}
          </div>

          {!isCollapsed && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                logout()
              }}
              className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition cursor-pointer"
              title="Cerrar sesión"
              aria-label="Cerrar sesión"
            >
              <LogOut className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </aside>
  )
}

export default AppSidebar

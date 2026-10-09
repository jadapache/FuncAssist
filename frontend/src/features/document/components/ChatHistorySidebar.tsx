import { useState } from 'react'
import {
  Plus,
  Search,
  MessageSquare,
  Trash2,
  Check,
  X,
  PanelLeftClose,
  PanelLeftOpen,
  Edit3,
} from 'lucide-react'
import type { ChatConversation } from '../../../features/document/hooks/useChatPersistence'

interface ChatHistorySidebarProps {
  conversations: ChatConversation[]
  activeConversationId: string | null
  isCollapsed: boolean
  onToggleCollapse: () => void
  onSelectConversation: (id: string) => void
  onCreateConversation: () => void
  onRenameConversation: (id: string, newName: string) => void
  onDeleteConversation: (id: string) => void
}

export const ChatHistorySidebar = ({
  conversations,
  activeConversationId,
  isCollapsed,
  onToggleCollapse,
  onSelectConversation,
  onCreateConversation,
  onRenameConversation,
  onDeleteConversation,
}: ChatHistorySidebarProps) => {
  const [searchQuery, setSearchQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')

  const filteredConversations = conversations.filter((c) =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase()),
  )

  const startEditing = (conv: ChatConversation) => {
    setEditingId(conv.id)
    setEditValue(conv.name)
  }

  const confirmEdit = (id: string) => {
    if (editValue.trim()) {
      onRenameConversation(id, editValue.trim())
    }
    setEditingId(null)
    setEditValue('')
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditValue('')
  }

  const formatDate = (isoString: string): string => {
    try {
      const date = new Date(isoString)
      const now = new Date()
      const diffMs = now.getTime() - date.getTime()
      const diffMinutes = diffMs / (1000 * 60)
      const diffHours = diffMs / (1000 * 60 * 60)

      if (diffMinutes < 2) return 'Hace un instante'
      if (diffMinutes < 60) return `Hace ${Math.floor(diffMinutes)}m`
      if (diffHours < 24) return `Hace ${Math.floor(diffHours)}h`

      const diffDays = Math.floor(diffHours / 24)
      if (diffDays === 1) return 'Ayer'
      if (diffDays < 7) return `Hace ${diffDays} días`

      return date.toLocaleDateString('es-CO', { day: '2-digit', month: 'short' })
    } catch {
      return ''
    }
  }

  // Collapsed state: just show toggle button
  if (isCollapsed) {
    return (
      <div className="w-10 bg-white border-r border-slate-200 flex flex-col items-center py-3 gap-3 shrink-0">
        <button
          type="button"
          onClick={onToggleCollapse}
          className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition cursor-pointer"
          title="Mostrar historial de chats"
        >
          <PanelLeftOpen className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onCreateConversation}
          className="p-1.5 rounded-lg text-[#002777] hover:bg-blue-50 transition cursor-pointer"
          title="Nueva conversación"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
    )
  }

  return (
    <div className="w-52 bg-white border-r border-slate-200 flex flex-col shrink-0 overflow-hidden">
      {/* Header */}
      <div className="p-3 border-b border-slate-200 space-y-2 shrink-0">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">Historial</span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onCreateConversation}
              className="p-1 rounded-md text-[#002777] hover:bg-blue-50 transition cursor-pointer"
              title="Nueva conversación"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={onToggleCollapse}
              className="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition cursor-pointer"
              title="Colapsar sidebar"
            >
              <PanelLeftClose className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-slate-400 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Buscar chat..."
            className="w-full text-[11px] pl-7 pr-2 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:ring-1 focus:ring-[#002777] focus:outline-none transition"
          />
        </div>
      </div>

      {/* Conversations List */}
      <div className="flex-1 overflow-y-auto py-1">
        {filteredConversations.length === 0 ? (
          <div className="px-3 py-8 text-center">
            <MessageSquare className="h-6 w-6 text-slate-300 mx-auto mb-2" />
            <p className="text-[11px] text-slate-400">
              {conversations.length === 0 ? 'Sin conversaciones' : 'Sin resultados'}
            </p>
          </div>
        ) : (
          filteredConversations.map((conv) => {
            const isActive = conv.id === activeConversationId
            const isEditing = editingId === conv.id

            return (
              <div
                key={conv.id}
                className={`group mx-1.5 mb-0.5 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-blue-50 border border-blue-200/80'
                    : 'hover:bg-slate-50 border border-transparent'
                }`}
              >
                {isEditing ? (
                  /* Inline rename */
                  <div className="p-2 flex items-center gap-1">
                    <input
                      type="text"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') confirmEdit(conv.id)
                        if (e.key === 'Escape') cancelEdit()
                      }}
                      autoFocus
                      className="flex-1 text-[11px] px-1.5 py-0.5 bg-white border border-slate-300 rounded focus:ring-1 focus:ring-[#002777] focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => confirmEdit(conv.id)}
                      className="p-0.5 text-emerald-600 hover:bg-emerald-50 rounded cursor-pointer"
                    >
                      <Check className="h-3 w-3" />
                    </button>
                    <button
                      type="button"
                      onClick={cancelEdit}
                      className="p-0.5 text-slate-400 hover:bg-slate-100 rounded cursor-pointer"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ) : (
                  /* Normal display */
                  <button
                    type="button"
                    onClick={() => onSelectConversation(conv.id)}
                    className="w-full text-left p-2 cursor-pointer"
                  >
                    <div className="flex items-start justify-between gap-1">
                      <div className="min-w-0 flex-1">
                        <p
                          className={`text-[11px] font-semibold truncate ${
                            isActive ? 'text-[#002777]' : 'text-slate-800'
                          }`}
                          title={conv.name}
                        >
                          {conv.name.length > 15 ? `${conv.name.slice(0, 15)}...` : conv.name}
                        </p>
                        <p className="text-[10px] text-slate-400 mt-0.5">
                          {formatDate(conv.lastInteraction)}
                          {conv.messages.length > 0 && (
                            <span className="ml-1">• {conv.messages.length} msg</span>
                          )}
                        </p>
                      </div>

                      {/* Action buttons (visible on hover) */}
                      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            startEditing(conv)
                          }}
                          className="p-0.5 rounded text-slate-400 hover:text-amber-600 hover:bg-amber-50 transition cursor-pointer"
                          title="Renombrar"
                        >
                          <Edit3 className="h-3 w-3" />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            onDeleteConversation(conv.id)
                          }}
                          className="p-0.5 rounded text-slate-400 hover:text-red-600 hover:bg-red-50 transition cursor-pointer"
                          title="Eliminar"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    </div>
                  </button>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core'
import { Check, Edit3, Loader2, MessageSquare, PanelLeftClose, PanelLeftOpen, Plus, Search, Trash2, X } from 'lucide'
import { AutoFocusDirective } from '../../../shared/directives/auto-focus.directive'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'
import type { ChatConversation } from '../types/chat'

/**
 * Port of React `ChatHistorySidebar` (exported by the chat feature; not mounted by `ChatWorkspace`).
 * Two-argument callback `onRenameConversation(id, newName)` emits `{ id, newName }`.
 */
@Component({
  selector: 'app-chat-history-sidebar',
  imports: [LucideIconDirective, AutoFocusDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    @if (isCollapsed()) {
      <!-- Collapsed state: just show toggle button -->
      <div class="w-10 bg-white border-r border-slate-200 flex flex-col items-center py-3 gap-3 shrink-0">
        <button
          type="button"
          (click)="onToggleCollapse.emit()"
          class="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition cursor-pointer"
          title="Mostrar historial de chats"
        >
          <svg [lucide]="icons.PanelLeftOpen" class="h-4 w-4"></svg>
        </button>
        <button
          type="button"
          (click)="onCreateConversation.emit()"
          class="p-1.5 rounded-lg text-[#002777] hover:bg-blue-50 transition cursor-pointer"
          title="Nueva conversación"
        >
          <svg [lucide]="icons.Plus" class="h-4 w-4"></svg>
        </button>
      </div>
    } @else {
      <div class="w-52 bg-white border-r border-slate-200 flex flex-col shrink-0 overflow-hidden">
        <!-- Header -->
        <div class="p-3 border-b border-slate-200 space-y-2 shrink-0">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold text-slate-700 uppercase tracking-wider">Historial</span>
            <div class="flex items-center gap-1">
              <button
                type="button"
                (click)="onCreateConversation.emit()"
                class="p-1 rounded-md text-[#002777] hover:bg-blue-50 transition cursor-pointer"
                title="Nueva conversación"
              >
                <svg [lucide]="icons.Plus" class="h-3.5 w-3.5"></svg>
              </button>
              <button
                type="button"
                (click)="onToggleCollapse.emit()"
                class="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition cursor-pointer"
                title="Colapsar sidebar"
              >
                <svg [lucide]="icons.PanelLeftClose" class="h-3.5 w-3.5"></svg>
              </button>
            </div>
          </div>

          <!-- Search -->
          <div class="relative">
            <svg
              [lucide]="icons.Search"
              class="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-slate-400 pointer-events-none"
            ></svg>
            <input
              type="text"
              [value]="searchQuery()"
              (input)="searchQuery.set($any($event.target).value)"
              placeholder="Buscar chat..."
              class="w-full text-[11px] pl-7 pr-2 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:ring-1 focus:ring-[#002777] focus:outline-none transition"
            />
          </div>
        </div>

        <!-- Conversations List -->
        <div class="flex-1 overflow-y-auto py-1">
          @if (filteredConversations().length === 0) {
            <div class="px-3 py-8 text-center">
              <svg [lucide]="icons.MessageSquare" class="h-6 w-6 text-slate-300 mx-auto mb-2"></svg>
              <p class="text-[11px] text-slate-400">
                {{ conversations().length === 0 ? 'Sin conversaciones' : 'Sin resultados' }}
              </p>
            </div>
          } @else {
            @for (conv of filteredConversations(); track conv.id) {
              @let isActive = conv.id === activeConversationId();
              <div
                [class]="
                  'group mx-1.5 mb-0.5 rounded-lg transition-colors ' +
                  (isActive ? 'bg-blue-50 border border-blue-200/80' : 'hover:bg-slate-50 border border-transparent')
                "
              >
                @if (editingId() === conv.id) {
                  <!-- Inline rename -->
                  <div class="p-2 flex items-center gap-1">
                    <input
                      type="text"
                      [value]="editValue()"
                      (input)="editValue.set($any($event.target).value)"
                      (keydown)="handleEditKeyDown($event, conv.id)"
                      appAutoFocus
                      class="flex-1 text-[11px] px-1.5 py-0.5 bg-white border border-slate-300 rounded focus:ring-1 focus:ring-[#002777] focus:outline-none"
                    />
                    <button
                      type="button"
                      (click)="confirmEdit(conv.id)"
                      class="p-0.5 text-emerald-600 hover:bg-emerald-50 rounded cursor-pointer"
                    >
                      <svg [lucide]="icons.Check" class="h-3 w-3"></svg>
                    </button>
                    <button
                      type="button"
                      (click)="cancelEdit()"
                      class="p-0.5 text-slate-400 hover:bg-slate-100 rounded cursor-pointer"
                    >
                      <svg [lucide]="icons.X" class="h-3 w-3"></svg>
                    </button>
                  </div>
                } @else {
                  <!-- Normal display -->
                  <button type="button" (click)="onSelectConversation.emit(conv.id)" class="w-full text-left p-2 cursor-pointer">
                    <div class="flex items-start justify-between gap-1">
                      <div class="min-w-0 flex-1">
                        <div class="flex items-center gap-1.5">
                          <p
                            [class]="'text-[11px] font-semibold truncate ' + (isActive ? 'text-[#002777]' : 'text-slate-800')"
                            [title]="conv.name"
                          >
                            {{ conv.name.length > 15 ? conv.name.slice(0, 15) + '...' : conv.name }}
                          </p>
                          @if (generatingConversationId() === conv.id) {
                            <svg [lucide]="icons.Loader2" class="h-2.5 w-2.5 animate-spin text-[#002777] shrink-0"></svg>
                          }
                        </div>
                        <p class="text-[10px] text-slate-400 mt-0.5">{{ formatDate(conv.lastInteraction) }}@if (conv.messages.length > 0) {<span class="ml-1">• {{ conv.messages.length }} msg</span>}</p>
                      </div>

                      <!-- Action buttons (visible on hover) -->
                      <div class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                        <button
                          type="button"
                          (click)="$event.stopPropagation(); startEditing(conv)"
                          class="p-0.5 rounded text-slate-400 hover:text-amber-600 hover:bg-amber-50 transition cursor-pointer"
                          title="Renombrar"
                        >
                          <svg [lucide]="icons.Edit3" class="h-3 w-3"></svg>
                        </button>
                        <button
                          type="button"
                          (click)="$event.stopPropagation(); onDeleteConversation.emit(conv.id)"
                          class="p-0.5 rounded text-slate-400 hover:text-red-600 hover:bg-red-50 transition cursor-pointer"
                          title="Eliminar"
                        >
                          <svg [lucide]="icons.Trash2" class="h-3 w-3"></svg>
                        </button>
                      </div>
                    </div>
                  </button>
                }
              </div>
            }
          }
        </div>
      </div>
    }
  `,
})
export class ChatHistorySidebarComponent {
  readonly conversations = input.required<ChatConversation[]>()
  readonly activeConversationId = input.required<string | null>()
  readonly generatingConversationId = input<string | null | undefined>(undefined)
  readonly isCollapsed = input.required<boolean>()

  readonly onToggleCollapse = output<void>()
  readonly onSelectConversation = output<string>()
  readonly onCreateConversation = output<void>()
  readonly onRenameConversation = output<{ id: string; newName: string }>()
  readonly onDeleteConversation = output<string>()

  protected readonly icons = {
    Check,
    Edit3,
    Loader2,
    MessageSquare,
    PanelLeftClose,
    PanelLeftOpen,
    Plus,
    Search,
    Trash2,
    X,
  }

  protected readonly searchQuery = signal('')
  protected readonly editingId = signal<string | null>(null)
  protected readonly editValue = signal('')

  protected readonly filteredConversations = computed(() =>
    this.conversations().filter((c) => c.name.toLowerCase().includes(this.searchQuery().toLowerCase())),
  )

  protected startEditing(conv: ChatConversation): void {
    this.editingId.set(conv.id)
    this.editValue.set(conv.name)
  }

  protected confirmEdit(id: string): void {
    if (this.editValue().trim()) {
      this.onRenameConversation.emit({ id, newName: this.editValue().trim() })
    }
    this.editingId.set(null)
    this.editValue.set('')
  }

  protected cancelEdit(): void {
    this.editingId.set(null)
    this.editValue.set('')
  }

  protected handleEditKeyDown(e: KeyboardEvent, id: string): void {
    if (e.key === 'Enter') this.confirmEdit(id)
    if (e.key === 'Escape') this.cancelEdit()
  }

  protected formatDate(isoString: string): string {
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
}

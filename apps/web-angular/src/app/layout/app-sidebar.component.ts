import { ChangeDetectionStrategy, Component, ElementRef, computed, inject, input, signal, viewChild } from '@angular/core'
import { Router, RouterLink } from '@angular/router'
import {
  BookOpen,
  Check,
  ChevronDown,
  CircleHelp,
  Edit3,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Mic,
  Plus,
  Search,
  Settings,
  Sparkles,
  Trash2,
  User,
  X,
} from 'lucide'
import type { UserRole } from '../api/client'
import { AuthService } from '../core/auth/auth.service'
import { UserService } from '../core/auth/user.service'
import { CurrentUrlService } from '../core/layout/current-url.service'
import { SidebarService } from '../core/layout/sidebar.service'
import { ChatStore } from '../features/chat/state/chat.store'
import type { ChatConversation } from '../features/chat/types/chat'
import { AutoFocusDirective } from '../shared/directives/auto-focus.directive'
import { LucideIconDirective } from '../shared/icons/lucide.directive'

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

const ACTIVE_ITEM = 'bg-blue-50 text-[#002777] shadow-xs ring-1 ring-blue-200 font-semibold'
const IDLE_ITEM = 'text-slate-600 hover:bg-slate-100/80 hover:text-slate-900'
const SUB_ACTIVE = 'bg-blue-50 text-[#002777] font-semibold'
const SUB_IDLE = 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'

/** Collapsible main navigation with chat history and profile popover (port of React `AppSidebar`). */
@Component({
  selector: 'app-sidebar',
  imports: [RouterLink, LucideIconDirective, AutoFocusDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents', '(document:mousedown)': 'onDocumentMouseDown($event)' },
  template: `
    <aside
      [class]="
        'relative flex flex-col shrink-0 border-r border-slate-200 bg-white/95 backdrop-blur-xl transition-all duration-300 z-30 select-none ' +
        (collapsed() ? 'w-16' : 'w-64')
      "
    >
      <!-- Top Header / Logo + Version -->
      <div
        [class]="
          'flex h-[54px] items-center border-b border-slate-200/80 shrink-0 ' +
          (collapsed() ? 'justify-center px-2' : 'px-4')
        "
      >
        <a routerLink="/" class="flex items-center gap-2.5 overflow-visible transition-all" title="FuncAssist">
          <div
            class="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#002777] to-[#004497] text-white shadow-md shadow-[#002777]/30 ring-1 ring-blue-100 overflow-visible"
          >
            <svg [lucide]="icons.Sparkles" class="h-4 w-4"></svg>
            <span
              class="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-cyan-400 ring-2 ring-white animate-pulse-soft z-10"
              aria-hidden="true"
            ></span>
          </div>
          @if (!collapsed()) {
            <div class="flex items-baseline gap-1.5 overflow-hidden">
              <span class="text-sm font-bold tracking-tight text-slate-900 whitespace-nowrap">
                Func<span class="font-normal text-blue-700">Assist</span>
              </span>
              @if (version()) {
                <span class="text-xs text-slate-500 font-normal font-mono whitespace-nowrap">v.{{ version() }}</span>
              }
            </div>
          }
        </a>
      </div>

      <!-- Main Navigation -->
      <nav class="flex-1 overflow-y-auto px-2 py-3 space-y-1 scrollbar-thin">
        <!-- Inicio -->
        <a
          routerLink="/"
          [class]="navItemClass(url.isActive('/', true))"
          [attr.aria-current]="url.isActive('/', true) ? 'page' : null"
          title="Inicio"
        >
          <svg [lucide]="icons.LayoutDashboard" class="h-4 w-4 shrink-0 opacity-70"></svg>
          @if (!collapsed()) {
            <span>Inicio</span>
          }
        </a>

        <!-- Chat Section -->
        <div>
          <div
            [class]="
              'flex items-center justify-between rounded-xl px-3 py-2 text-sm font-medium transition-all duration-200 cursor-pointer ' +
              (isChatActive() ? activeItem : idleItem) +
              ' ' +
              (collapsed() ? 'justify-center px-0' : '')
            "
            (click)="onChatHeaderClick()"
            title="Chat"
          >
            <div class="flex items-center gap-3 min-w-0">
              <svg [lucide]="icons.MessageSquare" class="h-4 w-4 shrink-0 opacity-70"></svg>
              @if (!collapsed()) {
                <span>Chat</span>
              }
            </div>

            @if (!collapsed()) {
              <div class="flex items-center gap-1" (click)="$event.stopPropagation()">
                <button
                  type="button"
                  (click)="handleCreateNewChat()"
                  class="p-1 rounded-md text-[#002777] hover:bg-blue-100/80 transition cursor-pointer"
                  title="Nuevo chat"
                  aria-label="Nuevo chat"
                >
                  <svg [lucide]="icons.Plus" class="h-3.5 w-3.5"></svg>
                </button>
                <button
                  type="button"
                  (click)="chatExpanded.set(!chatExpanded())"
                  class="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition cursor-pointer"
                  [title]="chatExpanded() ? 'Plegar chats' : 'Desplegar chats'"
                >
                  <svg
                    [lucide]="icons.ChevronDown"
                    [class]="'h-3.5 w-3.5 transition-transform duration-200 ' + (chatExpanded() ? 'rotate-180' : '')"
                  ></svg>
                </button>
              </div>
            }
          </div>

          <!-- Expanded Chat Sub-tree -->
          @if (!collapsed() && chatExpanded()) {
            <div class="mt-2 pl-2 pr-1 space-y-2">
              <div class="relative">
                <svg
                  [lucide]="icons.Search"
                  class="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400 pointer-events-none"
                ></svg>
                <input
                  type="text"
                  [value]="chat.searchQuery()"
                  (input)="chat.setSearchQuery($any($event.target).value)"
                  placeholder="Buscar chats..."
                  class="w-full text-xs pl-8 pr-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-800 placeholder-slate-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-[#002777] focus:border-blue-300 transition"
                />
              </div>

              <div class="px-1 pt-1">
                <p class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Recientes</p>
              </div>

              <div class="space-y-0.5 max-h-56 overflow-y-auto scrollbar-thin">
                @if (filteredConversations().length === 0) {
                  <p class="px-2 py-3 text-[11px] text-slate-400 italic text-center">
                    {{ chat.conversations().length === 0 ? 'Sin conversaciones' : 'Sin coincidencias' }}
                  </p>
                } @else {
                  @for (conv of filteredConversations(); track conv.id) {
                    @let isSelected = isChatActive() && conv.id === chat.activeConversationId();
                    @let isEditing = editingId() === conv.id;
                    <div
                      [class]="
                        'group relative flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs transition-colors cursor-pointer ' +
                        (isSelected
                          ? 'bg-blue-100/70 text-[#002777] font-semibold'
                          : 'text-slate-700 hover:bg-slate-100 hover:text-slate-900')
                      "
                      (click)="!isEditing && handleSelectChat(conv.id)"
                    >
                      @if (isEditing) {
                        <div class="flex items-center gap-1 w-full" (click)="$event.stopPropagation()">
                          <input
                            type="text"
                            appAutoFocus
                            [value]="editValue()"
                            (input)="editValue.set($any($event.target).value)"
                            (keydown.enter)="confirmEdit(conv.id)"
                            (keydown.escape)="cancelEdit()"
                            class="flex-1 text-xs px-1.5 py-0.5 bg-white text-slate-900 border border-[#002777] rounded focus:outline-none"
                          />
                          <button
                            type="button"
                            (click)="confirmEdit(conv.id)"
                            class="p-1 text-emerald-600 hover:bg-emerald-50 rounded"
                            title="Guardar"
                          >
                            <svg [lucide]="icons.Check" class="h-3 w-3"></svg>
                          </button>
                          <button
                            type="button"
                            (click)="cancelEdit()"
                            class="p-1 text-slate-400 hover:bg-slate-100 rounded"
                            title="Cancelar"
                          >
                            <svg [lucide]="icons.X" class="h-3 w-3"></svg>
                          </button>
                        </div>
                      } @else {
                        <div class="flex items-center gap-2 min-w-0 flex-1">
                          <svg [lucide]="icons.MessageSquare" class="h-3.5 w-3.5 shrink-0 opacity-50 text-[#002777]"></svg>
                          <span class="truncate" [title]="conv.name">{{ conv.name }}</span>
                        </div>
                        <div
                          class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 ml-1"
                          (click)="$event.stopPropagation()"
                        >
                          <button
                            type="button"
                            (click)="startEditing(conv)"
                            class="p-1 text-slate-400 hover:text-amber-600 rounded transition"
                            title="Renombrar chat"
                          >
                            <svg [lucide]="icons.Edit3" class="h-3 w-3"></svg>
                          </button>
                          <button
                            type="button"
                            (click)="chat.deleteConversation(conv.id)"
                            class="p-1 text-slate-400 hover:text-red-600 rounded transition"
                            title="Eliminar chat"
                          >
                            <svg [lucide]="icons.Trash2" class="h-3 w-3"></svg>
                          </button>
                        </div>
                      }
                    </div>
                  }
                }
              </div>
            </div>
          }
        </div>

        <!-- Transcripciones -->
        <a
          routerLink="/transcripciones"
          [class]="navItemClass(url.isActive('/transcripciones'))"
          [attr.aria-current]="url.isActive('/transcripciones') ? 'page' : null"
          title="Transcripciones"
        >
          <svg [lucide]="icons.Mic" class="h-4 w-4 shrink-0 opacity-70"></svg>
          @if (!collapsed()) {
            <span>Transcripciones</span>
          }
        </a>

        <!-- Conocimiento (Biblioteca + Consultar Producto) -->
        <div>
          <button
            type="button"
            (click)="onKnowledgeClick()"
            [class]="
              'w-full flex items-center justify-between rounded-xl px-3 py-2 text-sm font-medium transition-all duration-200 cursor-pointer ' +
              (isKnowledgeActive() ? activeItem : idleItem) +
              ' ' +
              (collapsed() ? 'justify-center px-0' : '')
            "
            title="Conocimiento"
          >
            <div class="flex items-center gap-3">
              <svg [lucide]="icons.BookOpen" class="h-4 w-4 shrink-0 opacity-70"></svg>
              @if (!collapsed()) {
                <span>Conocimiento</span>
              }
            </div>
            @if (!collapsed()) {
              <svg
                [lucide]="icons.ChevronDown"
                [class]="
                  'h-3.5 w-3.5 text-slate-400 transition-transform duration-200 ' +
                  (knowledgeExpanded() ? 'rotate-180' : '')
                "
              ></svg>
            }
          </button>

          @if (!collapsed() && knowledgeExpanded()) {
            <div class="mt-1 pl-6 space-y-0.5">
              <a
                routerLink="/knowledge"
                [class]="
                  'flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs transition-colors ' +
                  (url.isActive('/knowledge', true) ? subActive : subIdle)
                "
                [attr.aria-current]="url.isActive('/knowledge', true) ? 'page' : null"
              >
                <svg [lucide]="icons.BookOpen" class="h-3.5 w-3.5 shrink-0 opacity-60"></svg>
                <span>Biblioteca</span>
              </a>
              <a
                routerLink="/knowledge/ask"
                [class]="
                  'flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs transition-colors ' +
                  (url.isActive('/knowledge/ask') ? subActive : subIdle)
                "
                [attr.aria-current]="url.isActive('/knowledge/ask') ? 'page' : null"
              >
                <svg [lucide]="icons.CircleHelp" class="h-3.5 w-3.5 shrink-0 opacity-60"></svg>
                <span>Consultar Producto</span>
              </a>
            </div>
          }
        </div>

        <!-- Configuraciones -->
        <a
          routerLink="/settings"
          [class]="navItemClass(url.isActive('/settings'))"
          [attr.aria-current]="url.isActive('/settings') ? 'page' : null"
          title="Configuraciones"
        >
          <svg [lucide]="icons.Settings" class="h-4 w-4 shrink-0 opacity-70"></svg>
          @if (!collapsed()) {
            <span>Configuraciones</span>
          }
        </a>
      </nav>

      <!-- Footer Profile Section with Popover -->
      <div class="relative p-2.5 border-t border-slate-100 shrink-0" #profileRef>
        @if (profileMenuOpen()) {
          <div
            class="absolute left-3 bottom-16 w-56 rounded-2xl bg-white border border-slate-200 p-2 text-slate-800 shadow-xl z-50 animate-fadeIn"
          >
            <div class="flex items-center gap-2.5 p-2 rounded-xl bg-slate-50 border border-slate-100">
              <div
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#002777] to-[#004497] text-white font-extrabold text-xs shadow-md shadow-[#002777]/20"
              >
                {{ initials() }}
              </div>
              <div class="min-w-0 flex-1">
                <p class="text-xs font-bold text-slate-900 truncate" [title]="activeName()">{{ activeName() }}</p>
                <p class="text-[11px] font-semibold text-blue-700 truncate" [title]="roleLabel()">{{ roleLabel() }}</p>
              </div>
            </div>

            <div class="border-t border-slate-100 my-1.5"></div>

            <div class="space-y-0.5">
              <a
                routerLink="/profile"
                (click)="profileMenuOpen.set(false)"
                class="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-slate-700 hover:bg-slate-100 hover:text-slate-900 transition"
              >
                <svg [lucide]="icons.User" class="h-3.5 w-3.5 text-slate-500"></svg>
                <span>Perfil</span>
              </a>
              <button
                type="button"
                (click)="profileMenuOpen.set(false); auth.logout()"
                class="flex w-full items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-red-600 hover:bg-red-50 hover:text-red-700 transition cursor-pointer"
              >
                <svg [lucide]="icons.LogOut" class="h-3.5 w-3.5 text-red-500"></svg>
                <span>Cerrar sesión</span>
              </button>
            </div>
          </div>
        }

        <div
          (click)="profileMenuOpen.set(!profileMenuOpen())"
          [class]="
            'flex items-center justify-between gap-2.5 p-2 rounded-xl hover:bg-slate-100/80 transition cursor-pointer ' +
            (collapsed() ? 'justify-center px-0' : '')
          "
          [title]="activeName() + ' (' + roleLabel() + ')'"
        >
          <div class="flex items-center gap-2.5 min-w-0">
            <div
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#002777] to-[#004497] text-white font-extrabold text-xs shadow-md shadow-[#002777]/20 ring-2 ring-blue-100"
            >
              {{ initials() }}
            </div>
            @if (!collapsed()) {
              <div class="min-w-0 flex-1">
                <p class="text-xs font-bold text-slate-900 truncate" [title]="activeName()">{{ activeName() }}</p>
                <p class="text-[11px] font-semibold text-blue-700 truncate" [title]="roleLabel()">{{ roleLabel() }}</p>
              </div>
            }
          </div>

          @if (!collapsed()) {
            <button
              type="button"
              (click)="$event.stopPropagation(); auth.logout()"
              class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition cursor-pointer"
              title="Cerrar sesión"
              aria-label="Cerrar sesión"
            >
              <svg [lucide]="icons.LogOut" class="h-4 w-4"></svg>
            </button>
          }
        </div>
      </div>
    </aside>
  `,
})
export class AppSidebarComponent {
  readonly displayName = input.required<string>()
  readonly version = input<string | null>(null)

  protected readonly auth = inject(AuthService)
  protected readonly chat = inject(ChatStore)
  protected readonly url = inject(CurrentUrlService)
  private readonly sidebar = inject(SidebarService)
  private readonly userService = inject(UserService)
  private readonly router = inject(Router)
  private readonly profileRef = viewChild<ElementRef<HTMLDivElement>>('profileRef')

  protected readonly icons = {
    BookOpen,
    Check,
    ChevronDown,
    CircleHelp,
    Edit3,
    LayoutDashboard,
    LogOut,
    MessageSquare,
    Mic,
    Plus,
    Search,
    Settings,
    Sparkles,
    Trash2,
    User,
    X,
  }
  protected readonly activeItem = ACTIVE_ITEM
  protected readonly idleItem = IDLE_ITEM
  protected readonly subActive = SUB_ACTIVE
  protected readonly subIdle = SUB_IDLE

  protected readonly chatExpanded = signal(true)
  protected readonly knowledgeExpanded = signal(false)
  protected readonly profileMenuOpen = signal(false)
  protected readonly editingId = signal<string | null>(null)
  protected readonly editValue = signal('')

  protected readonly collapsed = this.sidebar.isCollapsed
  protected readonly activeName = computed(() => this.userService.user()?.display_name || this.displayName())
  protected readonly roleLabel = computed(() => {
    const role = (this.userService.user()?.user_role as UserRole) || 'admin'
    return roleLabels[role] || 'Administrador'
  })
  protected readonly initials = computed(() => getInitials(this.activeName()))

  protected readonly isChatActive = computed(() => this.url.pathname().startsWith('/chat'))
  protected readonly isKnowledgeActive = computed(() => this.url.pathname().startsWith('/knowledge'))

  protected readonly filteredConversations = computed(() => {
    const query = this.chat.searchQuery().toLowerCase()
    return this.chat.conversations().filter((c) => c.name.toLowerCase().includes(query))
  })

  protected navItemClass(isActive: boolean): string {
    return `flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-all duration-200 ${
      isActive ? ACTIVE_ITEM : IDLE_ITEM
    } ${this.collapsed() ? 'justify-center px-0' : ''}`
  }

  protected onDocumentMouseDown(event: MouseEvent): void {
    const ref = this.profileRef()?.nativeElement
    if (ref && !ref.contains(event.target as Node)) {
      this.profileMenuOpen.set(false)
    }
  }

  protected onChatHeaderClick(): void {
    if (this.collapsed()) {
      this.sidebar.toggleSidebar()
      this.chatExpanded.set(true)
      void this.router.navigateByUrl('/chat')
    } else {
      this.chatExpanded.set(!this.chatExpanded())
    }
  }

  protected onKnowledgeClick(): void {
    if (this.collapsed()) {
      this.sidebar.toggleSidebar()
      this.knowledgeExpanded.set(true)
    } else {
      this.knowledgeExpanded.set(!this.knowledgeExpanded())
    }
  }

  protected handleCreateNewChat(): void {
    this.chat.createConversation('Nueva conversación')
    if (!this.isChatActive()) {
      void this.router.navigateByUrl('/chat')
    }
  }

  protected handleSelectChat(id: string): void {
    this.chat.switchConversation(id)
    if (!this.isChatActive()) {
      void this.router.navigateByUrl(`/chat?session=${id}`)
    }
  }

  protected startEditing(conv: ChatConversation): void {
    this.editingId.set(conv.id)
    this.editValue.set(conv.name)
  }

  protected confirmEdit(id: string): void {
    const value = this.editValue().trim()
    if (value) this.chat.renameConversation(id, value)
    this.editingId.set(null)
    this.editValue.set('')
  }

  protected cancelEdit(): void {
    this.editingId.set(null)
    this.editValue.set('')
  }
}

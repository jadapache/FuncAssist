import { DestroyRef, Injectable, computed, effect, inject, signal, untracked } from '@angular/core'
import { NavigationEnd, Router } from '@angular/router'
import { filter } from 'rxjs'
import { AuthService } from '../../../core/auth/auth.service'
import { getAuthToken } from '../../../core/api/config'
import { draftsApi } from '../../document/api/draftsApi'
import { chatSessionsApi } from '../api/chatSessionsApi'
import type { ChatConversation, ChatConversationUpdate, ChatPersistMessage } from '../types/chat'

const FEATURE_SLUG = 'chat'

/**
 * Global chat conversation store.
 * Angular port of React `ChatContext` + `useChatPersistence('chat', user?.id)`:
 * - sessions are loaded from the backend (PostgreSQL) whenever the authenticated user changes;
 * - the active session is mirrored in the `?session=` query parameter (`?new=1` forces a new chat);
 * - changes are debounced (600 ms) and synced back as drafts.
 */
@Injectable({ providedIn: 'root' })
export class ChatStore {
  private readonly router = inject(Router)
  private readonly auth = inject(AuthService)

  readonly conversations = signal<ChatConversation[]>([])
  readonly activeConversationId = signal<string | null>(null)
  readonly searchQuery = signal('')
  readonly activeConversation = computed(
    () => this.conversations().find((c) => c.id === this.activeConversationId()) ?? null,
  )

  /** Session id requested by the current URL (`?session=`), ignored when `?new=1` is present. */
  private readonly urlSessionId = signal<string | null>(null)

  // Snapshot of the URL when the store was created (React captured it in refs at provider mount).
  private readonly initialUrlSessionId: string | null
  private readonly isExplicitNewAtStart: boolean
  private hasLocalConversation = false
  private loadGeneration = 0
  private readonly lastSyncedHash: Record<string, string> = {}
  private syncTimer: ReturnType<typeof setTimeout> | null = null

  constructor() {
    const params = new URLSearchParams(window.location.search)
    this.isExplicitNewAtStart = isExplicitNew(params)
    this.initialUrlSessionId = this.isExplicitNewAtStart ? null : params.get('session')
    this.activeConversationId.set(this.initialUrlSessionId)
    this.urlSessionId.set(this.initialUrlSessionId)

    const navSub = this.router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe(() => {
      const query = this.router.parseUrl(this.router.url).queryParamMap
      const explicitNew = query.get('new') === '1' || query.get('new') === 'true'
      this.urlSessionId.set(explicitNew ? null : query.get('session'))
    })
    inject(DestroyRef).onDestroy(() => {
      navSub.unsubscribe()
      if (this.syncTimer) clearTimeout(this.syncTimer)
    })

    // Reload sessions whenever the authenticated user changes.
    effect(() => {
      const userId = this.auth.user()?.id ?? null
      untracked(() => this.loadSessions(userId))
    })

    // Follow external URL changes (history navigation, links with ?session=).
    effect(() => {
      const urlSessionId = this.urlSessionId()
      const conversations = this.conversations()
      const activeId = this.activeConversationId()
      if (urlSessionId && urlSessionId !== activeId && conversations.some((c) => c.id === urlSessionId)) {
        untracked(() => this.activeConversationId.set(urlSessionId))
      }
    })

    // Debounced background sync of non-empty conversations to the backend.
    effect(() => {
      const conversations = this.conversations()
      untracked(() => this.scheduleSync(conversations))
    })
  }

  private loadSessions(_userId: string | null): void {
    const generation = ++this.loadGeneration
    // React fired this request even before login (and swallowed the 401); skip it when there is no token.
    if (!getAuthToken()) return

    chatSessionsApi
      .getSessions(FEATURE_SLUG)
      .then((remoteSessions: ChatConversation[]) => {
        if (generation !== this.loadGeneration) return
        this.conversations.update((current) => {
          const remoteIds = new Set(remoteSessions.map((conversation) => conversation.id))
          const localOnly = current.filter((conversation) => !remoteIds.has(conversation.id))
          // Deduplicate messages within remoteSessions to ensure no duplicates are loaded
          const cleanedRemote = remoteSessions.map((sess) => {
            const seen = new Set<string>()
            const dedupedMessages = sess.messages.filter((m: ChatPersistMessage) => {
              const key = m.id ? m.id : `${m.role}-${m.content.trim()}`
              if (seen.has(key)) return false
              seen.add(key)
              return true
            })
            return { ...sess, messages: dedupedMessages }
          })
          return [...localOnly, ...cleanedRemote].sort(
            (a, b) => new Date(b.lastInteraction).getTime() - new Date(a.lastInteraction).getTime(),
          )
        })

        if (this.isExplicitNewAtStart) {
          const newConv = buildConversation('Nueva conversación')
          this.conversations.update((current) => [newConv, ...current])
          this.hasLocalConversation = true
          this.activeConversationId.set(newConv.id)
          this.syncUrlSession(newConv.id)
          return
        }

        const matched = this.initialUrlSessionId
          ? remoteSessions.find((c) => c.id === this.initialUrlSessionId)
          : null

        if (!this.hasLocalConversation && !matched) {
          const fallbackId = remoteSessions[0]?.id || null
          this.activeConversationId.set(fallbackId)
          if (fallbackId && !this.initialUrlSessionId) {
            this.syncUrlSession(fallbackId)
          }
        }
      })
      .catch((err: unknown) => {
        console.debug('[ChatStore] Failed to fetch remote sessions:', err)
      })
  }

  private scheduleSync(conversations: ChatConversation[]): void {
    if (this.syncTimer) clearTimeout(this.syncTimer)
    const nonEmpties = conversations.filter((c) => c.messages.length > 0 || (c.artifacts && c.artifacts.length > 0))
    this.syncTimer = setTimeout(() => {
      nonEmpties.forEach((conv) => {
        const hash = `${conv.messages.length}-${(conv.artifacts || []).length}-${(conv.documentContent || '').length}`
        if (this.lastSyncedHash[conv.id] === hash) return
        this.lastSyncedHash[conv.id] = hash
        draftsApi
          .saveDraft({
            id: conv.id,
            name: conv.name,
            title: conv.name,
            feature_slug: FEATURE_SLUG,
            specification: FEATURE_SLUG,
            lastInteraction: conv.lastInteraction,
            messages: conv.messages,
            documentContent: conv.documentContent,
            artifacts: conv.artifacts,
          })
          .catch((err) => {
            console.debug('[ChatStore] Draft background sync failed:', err)
          })
      })
    }, 600)
  }

  /** Mirror the active session in `?session=` on the current route (replaces history entry). */
  private syncUrlSession(sessionId: string | null): void {
    const tree = this.router.parseUrl(this.router.url)
    const queryParams = { ...tree.queryParams }
    delete queryParams['new']
    if (sessionId) queryParams['session'] = sessionId
    else delete queryParams['session']
    tree.queryParams = queryParams
    void this.router.navigateByUrl(tree, { replaceUrl: true })
  }

  /** Create a brand new conversation and set it as active. */
  createConversation(name?: string): ChatConversation {
    const newConv = buildConversation(name || `Conversación ${this.conversations().length + 1}`)
    this.conversations.update((prev) => [newConv, ...prev])
    this.hasLocalConversation = true
    this.activeConversationId.set(newConv.id)
    this.syncUrlSession(newConv.id)
    return newConv
  }

  /** Update the active (or explicitly specified) conversation. */
  updateConversation(updates: ChatConversationUpdate, targetId?: string): void {
    const idToUpdate = targetId ?? this.activeConversationId()
    if (!idToUpdate) return
    this.conversations.update((prev) =>
      prev.map((c) =>
        c.id === idToUpdate
          ? { ...c, ...updates, lastInteraction: updates.lastInteraction ?? c.lastInteraction }
          : c,
      ),
    )
  }

  renameConversation(id: string, newName: string): void {
    this.conversations.update((prev) => prev.map((c) => (c.id === id ? { ...c, name: newName } : c)))
  }

  deleteConversation(id: string): void {
    const filtered = this.conversations().filter((c) => c.id !== id)
    this.conversations.set(filtered)
    if (this.activeConversationId() === id) {
      const nextId = filtered.length > 0 ? filtered[0].id : null
      this.activeConversationId.set(nextId)
      this.syncUrlSession(nextId)
    }
    draftsApi.deleteDraft(id).catch((err: unknown) => {
      console.debug('[ChatStore] Delete draft error:', err)
    })
    chatSessionsApi.deleteSession(id).catch((err: unknown) => {
      console.debug('[ChatStore] Delete chat session error:', err)
    })
  }

  switchConversation(id: string): void {
    this.activeConversationId.set(id)
    this.syncUrlSession(id)
  }

  setSearchQuery(query: string): void {
    this.searchQuery.set(query)
  }
}

function isExplicitNew(params: URLSearchParams): boolean {
  return params.get('new') === '1' || params.get('new') === 'true'
}

function buildConversation(name: string): ChatConversation {
  return {
    id: crypto.randomUUID(),
    name,
    lastInteraction: new Date().toISOString(),
    messages: [],
    documentContent: '',
    artifacts: [],
    activeArtifactId: undefined,
  }
}

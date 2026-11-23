/**
 * Servicio para gestionar el ciclo de vida de artefactos dentro de una conversación activa.
 * Encapsula: crear, eliminar, renombrar, actualizar contenido y selección activa.
 *
 * Angular port of React `useArtifacts`. Per-component state → `@Injectable()` without `providedIn`;
 * the consumer lists it in `providers` and calls `init(options)` once (reactive options are getters/signals).
 */
import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core'
import { ToastService } from '../../../core/notifications/toast.service'
import type { Artifact } from '../../../types/artifacts'
import type { DocumentArtifact } from '../types/chat'

export interface ArtifactsOptions {
  conversationArtifacts: () => DocumentArtifact[]
  onUpdateConversation: (
    updates: { artifacts: DocumentArtifact[]; documentContent?: string; activeArtifactId?: string },
    targetId?: string,
  ) => void
  currentConversationId?: () => string | null
}

@Injectable()
export class ArtifactsService {
  private readonly toast = inject(ToastService).toast
  private readonly options = signal<ArtifactsOptions | null>(null)

  readonly artifacts = computed<Artifact[]>(() => (this.options()?.conversationArtifacts() || []) as Artifact[])

  private readonly _activeArtifactId = signal<string | null>(null)
  readonly activeArtifactId = this._activeArtifactId.asReadonly()

  readonly activeArtifact = computed(() => {
    const artifacts = this.artifacts()
    const activeArtifactId = this._activeArtifactId()
    return artifacts.find((a) => a.id === activeArtifactId) ?? artifacts[0] ?? null
  })

  constructor() {
    // Sync when artifacts list changes externally
    effect(() => {
      const artifacts = this.artifacts()
      const activeArtifactId = this._activeArtifactId()
      untracked(() => {
        if (artifacts.length > 0) {
          if (!activeArtifactId || !artifacts.some((a) => a.id === activeArtifactId)) {
            this._activeArtifactId.set(artifacts[0].id)
          }
        } else {
          this._activeArtifactId.set(null)
        }
      })
    })
  }

  /** Hook options (React `useArtifacts({...})`). */
  init(options: ArtifactsOptions): void {
    this.options.set(options)
    this._activeArtifactId.set(untracked(() => this.artifacts())[0]?.id ?? null)
  }

  private get currentConversationId(): string | undefined {
    return this.options()?.currentConversationId?.() ?? undefined
  }

  private updateConversation(
    updates: { artifacts: DocumentArtifact[]; documentContent?: string; activeArtifactId?: string },
    targetId?: string,
  ): void {
    this.options()?.onUpdateConversation(updates, targetId)
  }

  setActiveArtifactId = (id: string | null): void => {
    this._activeArtifactId.set(id)
  }

  createArtifact = (title?: string, extension: Artifact['extension'] = 'docx'): string => {
    const artifacts = this.artifacts()
    const newId = crypto.randomUUID()
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    const newArt: Artifact = {
      id: newId,
      title: title ?? `Documento ${artifacts.length + 1}`,
      subtitle: 'Creado manualmente',
      extension,
      content: `# ${title ?? 'Nuevo Documento'}\n\nEscribe aquí el contenido...`,
      createdAt: now,
      updatedAt: 'Hace un momento',
    }
    const updated = [newArt, ...artifacts]
    this.updateConversation({ artifacts: updated as DocumentArtifact[], activeArtifactId: newId }, this.currentConversationId)
    this._activeArtifactId.set(newId)
    this.toast.success('Nuevo documento creado en Artefactos')
    return newId
  }

  deleteArtifact = (id: string): void => {
    const artifacts = this.artifacts()
    const activeArtifactId = this._activeArtifactId()
    if (artifacts.length <= 1) {
      this.toast.error('No puedes eliminar el único artefacto activo')
      return
    }
    const updated = artifacts.filter((a) => a.id !== id)
    const nextActiveId = activeArtifactId === id ? updated[0].id : activeArtifactId
    this.updateConversation(
      { artifacts: updated as DocumentArtifact[], activeArtifactId: nextActiveId || undefined },
      this.currentConversationId,
    )
    if (activeArtifactId === id) {
      this._activeArtifactId.set(updated[0].id)
    }
    this.toast.success('Artefacto eliminado')
  }

  renameArtifact = (id: string, newTitle: string): void => {
    const updated = this.artifacts().map((a) => (a.id === id ? { ...a, title: newTitle } : a))
    this.updateConversation({ artifacts: updated as DocumentArtifact[] }, this.currentConversationId)
  }

  updateArtifactContent = (id: string, content: string): void => {
    const updated = this.artifacts().map((a) => (a.id === id ? { ...a, content, updatedAt: 'Hace un momento' } : a))
    this.updateConversation({ artifacts: updated as DocumentArtifact[], documentContent: content }, this.currentConversationId)
  }

  setArtifactsFromGeneration = (newArtifacts: Artifact[]): void => {
    this.updateConversation(
      {
        artifacts: newArtifacts as DocumentArtifact[],
        documentContent: newArtifacts[0]?.content ?? '',
        activeArtifactId: newArtifacts[0]?.id,
      },
      this.currentConversationId,
    )
    if (newArtifacts[0]) this._activeArtifactId.set(newArtifacts[0].id)
  }
}

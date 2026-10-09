/**
 * Hook para gestionar el ciclo de vida de artefactos dentro de una conversación activa.
 * Encapsula: crear, eliminar, renombrar, actualizar contenido y selección activa.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useToast } from '../../../context/ToastContext'
import type { Artifact } from '../../../types/artifacts'
import type { DocumentArtifact } from './useChatPersistence'

interface UseArtifactsOptions {
  conversationArtifacts: DocumentArtifact[]
  onUpdateConversation: (updates: { artifacts: DocumentArtifact[]; documentContent?: string }) => void
}

export function useArtifacts({ conversationArtifacts, onUpdateConversation }: UseArtifactsOptions) {
  const { toast } = useToast()

  const artifacts: Artifact[] = useMemo(() => (conversationArtifacts || []) as Artifact[], [conversationArtifacts])

  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(
    () => artifacts[0]?.id ?? null,
  )

  const activeArtifact = useMemo(
    () => artifacts.find((a) => a.id === activeArtifactId) ?? artifacts[0] ?? null,
    [artifacts, activeArtifactId],
  )

  // Sync when artifacts list changes externally
  useEffect(() => {
    if (artifacts.length > 0) {
      if (!activeArtifactId || !artifacts.some((a) => a.id === activeArtifactId)) {
        setActiveArtifactId(artifacts[0].id)
      }
    } else {
      setActiveArtifactId(null)
    }
  }, [artifacts, activeArtifactId])

  const createArtifact = useCallback(
    (title?: string, extension: Artifact['extension'] = 'docx') => {
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
      onUpdateConversation({ artifacts: updated as DocumentArtifact[] })
      setActiveArtifactId(newId)
      toast.success('Nuevo documento creado en Artefactos')
      return newId
    },
    [artifacts, onUpdateConversation, toast],
  )

  const deleteArtifact = useCallback(
    (id: string) => {
      if (artifacts.length <= 1) {
        toast.error('No puedes eliminar el único artefacto activo')
        return
      }
      const updated = artifacts.filter((a) => a.id !== id)
      onUpdateConversation({ artifacts: updated as DocumentArtifact[] })
      if (activeArtifactId === id) {
        setActiveArtifactId(updated[0].id)
      }
      toast.success('Artefacto eliminado')
    },
    [artifacts, activeArtifactId, onUpdateConversation, toast],
  )

  const renameArtifact = useCallback(
    (id: string, newTitle: string) => {
      const updated = artifacts.map((a) => (a.id === id ? { ...a, title: newTitle } : a))
      onUpdateConversation({ artifacts: updated as DocumentArtifact[] })
    },
    [artifacts, onUpdateConversation],
  )

  const updateArtifactContent = useCallback(
    (id: string, content: string) => {
      const updated = artifacts.map((a) =>
        a.id === id ? { ...a, content, updatedAt: 'Hace un momento' } : a,
      )
      onUpdateConversation({ artifacts: updated as DocumentArtifact[], documentContent: content })
    },
    [artifacts, onUpdateConversation],
  )

  const setArtifactsFromGeneration = useCallback(
    (newArtifacts: Artifact[]) => {
      onUpdateConversation({
        artifacts: newArtifacts as DocumentArtifact[],
        documentContent: newArtifacts[0]?.content ?? '',
      })
      if (newArtifacts[0]) setActiveArtifactId(newArtifacts[0].id)
    },
    [onUpdateConversation],
  )

  return {
    artifacts,
    activeArtifact,
    activeArtifactId,
    setActiveArtifactId,
    createArtifact,
    deleteArtifact,
    renameArtifact,
    updateArtifactContent,
    setArtifactsFromGeneration,
  }
}

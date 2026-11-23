import { Injectable, inject, signal } from '@angular/core'
import { ToastService } from '../../../core/notifications/toast.service'
import { docAgentApi, type EphemeralAttachmentDoc } from '../api/docAgentApi'
import type { DomRef } from '../types/domRef'

export interface AttachedImage {
  id: string
  name: string
  dataUrl: string
  size: number
}

/**
 * Angular port of React `useChatAttachments(fileInputRef)`: ephemeral chat attachments.
 * Images are read locally as data URLs; documents are parsed by the backend (`parse-attachment`).
 * Per-component state → `@Injectable()`; call `init(fileInputRef)` once.
 */
@Injectable()
export class ChatAttachmentsService {
  private readonly toast = inject(ToastService).toast
  private fileInputRef: DomRef<HTMLInputElement> | null = null

  private readonly _uploadedDocs = signal<EphemeralAttachmentDoc[]>([])
  private readonly _uploading = signal(false)
  private readonly _attachedImages = signal<AttachedImage[]>([])

  readonly uploadedDocs = this._uploadedDocs.asReadonly()
  readonly uploading = this._uploading.asReadonly()
  readonly attachedImages = this._attachedImages.asReadonly()

  /** Hook parameter (React `useChatAttachments(fileInputRef)`). */
  init(fileInputRef: DomRef<HTMLInputElement>): void {
    this.fileInputRef = fileInputRef
  }

  handlePickFiles = async (picked: FileList | File[] | null): Promise<void> => {
    if (!picked || !picked.length) return
    const files = Array.from(picked)
    const imageFiles = files.filter((f) => f.type.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp)$/i.test(f.name))
    const docFiles = files.filter((f) => !f.type.startsWith('image/') && !/\.(png|jpe?g|webp|gif|bmp)$/i.test(f.name))

    if (imageFiles.length > 0) {
      for (const img of imageFiles) {
        const reader = new FileReader()
        reader.onload = () => {
          if (typeof reader.result === 'string') {
            this._attachedImages.update((prev) => [
              ...prev,
              {
                id: crypto.randomUUID(),
                name: img.name,
                dataUrl: reader.result as string,
                size: img.size,
              },
            ])
          }
        }
        reader.readAsDataURL(img)
      }
    }

    if (docFiles.length > 0) {
      this._uploading.set(true)
      try {
        const parsed = await Promise.all(docFiles.map((file) => docAgentApi.parseAttachment(file)))
        this._uploadedDocs.update((prev) => [...prev, ...parsed])
      } catch (err) {
        this.toast.error(err instanceof Error ? err.message : 'Error al procesar los documentos adjuntos')
      } finally {
        this._uploading.set(false)
      }
    }
    if (this.fileInputRef?.current) this.fileInputRef.current.value = ''
  }

  handleRemoveUploaded = (id: string): void => {
    this._uploadedDocs.update((prev) => prev.filter((d) => d.id !== id))
  }

  handleRemoveImage = (id: string): void => {
    this._attachedImages.update((prev) => prev.filter((i) => i.id !== id))
  }

  resetAttachments = (): void => {
    this._attachedImages.set([])
    this._uploadedDocs.set([])
  }
}

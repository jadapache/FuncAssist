import { useState, type RefObject } from 'react'
import { docAgentApi, type EphemeralAttachmentDoc } from '../api/docAgentApi'
import { useToast } from '../../../context/ToastContext'

export interface AttachedImage {
  id: string
  name: string
  dataUrl: string
  size: number
}

export function useChatAttachments(fileInputRef: RefObject<HTMLInputElement | null>) {
  const { toast } = useToast()
  const [uploadedDocs, setUploadedDocs] = useState<EphemeralAttachmentDoc[]>([])
  const [uploading, setUploading] = useState(false)
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([])

  const handlePickFiles = async (picked: FileList | File[] | null) => {
    if (!picked || !picked.length) return
    const files = Array.from(picked)
    const imageFiles = files.filter(
      (f) => f.type.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp)$/i.test(f.name),
    )
    const docFiles = files.filter(
      (f) => !f.type.startsWith('image/') && !/\.(png|jpe?g|webp|gif|bmp)$/i.test(f.name),
    )

    if (imageFiles.length > 0) {
      for (const img of imageFiles) {
        const reader = new FileReader()
        reader.onload = () => {
          if (typeof reader.result === 'string') {
            setAttachedImages((prev) => [
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
      setUploading(true)
      try {
        const parsed = await Promise.all(
          docFiles.map((file) => docAgentApi.parseAttachment(file)),
        )
        setUploadedDocs((prev) => [...prev, ...parsed])
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Error al procesar los documentos adjuntos')
      } finally {
        setUploading(false)
      }
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleRemoveUploaded = (id: string) => {
    setUploadedDocs((prev) => prev.filter((d) => d.id !== id))
  }

  const handleRemoveImage = (id: string) => {
    setAttachedImages((prev) => prev.filter((i) => i.id !== id))
  }

  const resetAttachments = () => {
    setAttachedImages([])
    setUploadedDocs([])
  }

  return {
    uploadedDocs,
    uploading,
    attachedImages,
    handlePickFiles,
    handleRemoveUploaded,
    handleRemoveImage,
    resetAttachments,
  }
}

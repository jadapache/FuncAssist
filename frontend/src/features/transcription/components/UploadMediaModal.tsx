import React from 'react'
import { X } from 'lucide-react'
import { UploadArea, type UploadTarget } from './UploadArea'

interface UploadMediaModalProps {
  isOpen: boolean
  onClose: () => void
  onUpload: (target: UploadTarget, title: string, description?: string) => Promise<void>
  isUploading?: boolean
  configuredModelLabel?: string
}

export const UploadMediaModal: React.FC<UploadMediaModalProps> = ({
  isOpen,
  onClose,
  onUpload,
  isUploading = false,
  configuredModelLabel,
}) => {
  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl bg-white rounded-3xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-7 py-5 border-b border-slate-100 shrink-0 bg-slate-50/50">
          <div>
            <h3 className="text-lg font-bold text-slate-900 mt-1">Nueva Transcripción</h3>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={isUploading}
            className="p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-xl transition cursor-pointer disabled:opacity-50"
            title="Cerrar modal"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-7 overflow-y-auto max-h-[80vh]">
          <UploadArea
            onUpload={async (target, title, desc) => {
              onClose()
              await onUpload(target, title, desc)
            }}
            isUploading={isUploading}
            configuredModelLabel={configuredModelLabel}
          />
        </div>
      </div>
    </div>
  )
}

import React from 'react'
import { Download, X, Sparkles, RefreshCw } from 'lucide-react'
import type { UpdateInfo } from '../hooks/useAppUpdater'

interface UpdateNotificationProps {
  updateInfo: UpdateInfo | null
  onInstall: () => void
  onDismiss: () => void
  isInstalling?: boolean
}

export const UpdateNotification: React.FC<UpdateNotificationProps> = ({
  updateInfo,
  onInstall,
  onDismiss,
  isInstalling = false,
}) => {
  if (!updateInfo?.available) return null

  return (
    <aside
      role="region"
      aria-label="Notificación de actualización disponible"
      className="fixed bottom-6 right-6 max-w-md w-full mx-4 sm:mx-0 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md rounded-2xl shadow-2xl border border-blue-200 dark:border-blue-900 p-5 space-y-4 z-50 animate-in fade-in slide-in-from-bottom-5 duration-300"
    >
      <div className="flex items-start gap-3">
        <div className="p-2.5 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-white shadow-md shadow-blue-500/20 shrink-0">
          <Sparkles className="h-5 w-5 animate-pulse" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-bold text-slate-900 dark:text-slate-100 text-base">
              Actualización disponible
            </h3>
            <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300">
              v{updateInfo.version}
            </span>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
            Una nueva versión de QA Project Management está lista para ser instalada.
          </p>
          {updateInfo.releaseNotes && (
            <div className="mt-2 text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/60 rounded-lg p-2.5 max-h-24 overflow-y-auto border border-slate-100 dark:border-slate-800">
              <p className="font-semibold text-slate-700 dark:text-slate-300 mb-0.5">Novedades:</p>
              <div className="whitespace-pre-wrap">{updateInfo.releaseNotes}</div>
            </div>
          )}
        </div>

        <button
          onClick={onDismiss}
          className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 rounded-lg transition-colors"
          title="Cerrar notificación"
          aria-label="Cerrar notificación"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex items-center gap-3 pt-1">
        <button
          onClick={onInstall}
          disabled={isInstalling}
          className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl font-semibold hover:from-blue-700 hover:to-indigo-700 shadow-md shadow-blue-500/20 active:scale-[0.98] transition-all disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer text-sm"
        >
          {isInstalling ? (
            <>
              <RefreshCw className="h-4 w-4 animate-spin" />
              <span>Instalando...</span>
            </>
          ) : (
            <>
              <Download className="h-4 w-4" />
              <span>Actualizar ahora</span>
            </>
          )}
        </button>

        <button
          onClick={onDismiss}
          disabled={isInstalling}
          className="px-4 py-2.5 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 rounded-xl font-medium hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors cursor-pointer text-sm disabled:opacity-50"
        >
          Más tarde
        </button>
      </div>
    </aside>
  )
}

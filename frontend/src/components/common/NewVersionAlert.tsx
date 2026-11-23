import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { useNewVersionAvailable } from './useNewVersionAvailable'

/** Asks the user to reload when a new frontend build has been deployed while this tab was open. */
export const NewVersionAlert = () => {
  const available = useNewVersionAvailable()
  const [dismissed, setDismissed] = useState(false)
  if (!available || dismissed) return null

  return (
    <div
      role="status"
      className="fixed bottom-4 left-1/2 z-[100] flex w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-200 bg-white px-4 py-3 text-sm text-slate-800 shadow-lg"
    >
      <span>Hay una nueva versión de la aplicación. Recarga la página para usarla.</span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-500 hover:bg-slate-100"
        >
          Más tarde
        </button>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="inline-flex items-center gap-1.5 rounded-lg bg-[#002777] px-3 py-1.5 text-xs font-bold text-white hover:bg-[#001f5f]"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Recargar
        </button>
      </div>
    </div>
  )
}

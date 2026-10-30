import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, Circle, Sliders, X } from 'lucide-react'

export interface ConfigProgressItem {
  id: string
  label: string
  description: string
  done: boolean
  tabTarget?: 'ai_providers' | 'integrations' | 'mcp' | 'personal'
}

export interface SystemConfigProgressBadgeProps {
  items: ConfigProgressItem[]
  progressPercentage: number
  onNavigateTab?: (tab: 'ai_providers' | 'integrations' | 'mcp' | 'personal') => void
}

export const SystemConfigProgressBadge = ({
  items,
  progressPercentage,
  onNavigateTab,
}: SystemConfigProgressBadgeProps) => {
  const [isOpen, setIsOpen] = useState(false)
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleMouseEnter = () => {
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current)
      hoverTimeoutRef.current = null
    }
    setIsOpen(true)
  }

  const handleMouseLeave = () => {
    hoverTimeoutRef.current = setTimeout(() => {
      setIsOpen(false)
    }, 250)
  }

  useEffect(() => {
    return () => {
      if (hoverTimeoutRef.current) {
        clearTimeout(hoverTimeoutRef.current)
      }
    }
  }, [])

  return (
    <div
      ref={containerRef}
      className="relative inline-flex"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        className="inline-flex items-center gap-2 rounded-full border border-blue-200/80 bg-blue-50/90 px-3 py-1 text-xs font-semibold text-[#002777] shadow-2xs hover:bg-blue-100 hover:border-blue-300 transition-colors cursor-pointer"
      >
        <Sliders className="h-3.5 w-3.5 text-[#002777]" aria-hidden />
        <span>Progreso de configuración del sistema</span>
        <span className="rounded-full bg-[#002777] px-2 py-0.5 text-[11px] font-bold text-white shadow-2xs">
          {progressPercentage}%
        </span>
      </button>

      {isOpen && (
        <div
          role="dialog"
          aria-label="Detalle de progreso de configuración del sistema"
          className="absolute left-0 top-full z-50 mt-2 w-80 sm:w-96 rounded-2xl border border-slate-200 bg-white p-5 shadow-xl ring-1 ring-black/5 animate-in fade-in zoom-in-95 duration-150"
        >
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h4 className="text-sm font-bold text-slate-900">
                Progreso de configuración del sistema
              </h4>
              <p className="text-xs text-slate-500">
                Estado de componentes clave del entorno
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
              aria-label="Cerrar detalle"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-3.5 space-y-1.5">
            <div className="flex items-center justify-between text-xs font-medium text-slate-600">
              <span>Completitud general</span>
              <span className="font-bold text-[#002777]">{progressPercentage}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-gradient-to-r from-blue-600 to-cyan-500 transition-all duration-500"
                style={{ width: `${progressPercentage}%` }}
              />
            </div>
          </div>

          <ul className="mt-4 divide-y divide-slate-100">
            {items.map((item) => (
              <li key={item.id} className="flex items-center justify-between py-2.5">
                <div className="pr-2 min-w-0">
                  <p className="text-xs font-semibold text-slate-800 truncate">
                    {item.label}
                  </p>
                  <p className="text-[11px] text-slate-500 truncate">
                    {item.description}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span
                    className={[
                      'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold',
                      item.done
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : 'bg-slate-100 text-slate-600 border border-slate-200',
                    ].join(' ')}
                  >
                    {item.done ? (
                      <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                    ) : (
                      <Circle className="h-3 w-3 text-slate-400" />
                    )}
                    {item.done ? 'Hecho' : 'No hecho'}
                  </span>
                  {item.tabTarget && onNavigateTab && !item.done && (
                    <button
                      type="button"
                      onClick={() => {
                        setIsOpen(false)
                        onNavigateTab(item.tabTarget!)
                      }}
                      className="text-[11px] font-medium text-blue-600 hover:text-blue-800 underline cursor-pointer"
                    >
                      Configurar
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

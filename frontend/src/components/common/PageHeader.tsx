import type { ReactNode } from 'react'
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useSidebar } from '../../context/SidebarContext'

interface PageHeaderProps {
  /**
   * Supertítulo / Eyebrow opcional (obsoleto en el diseño minimalista, pero conservado opcionalmente)
   */
  eyebrow?: string
  /**
   * Insignia / Badge opcional
   */
  badge?: ReactNode
  /**
   * Título principal de la página (h1 / header label)
   */
  title: string
  /**
   * Subtítulo o descripción (obsoleto en el diseño minimalista, pero conservado opcionalmente)
   */
  subtitle?: string | ReactNode
  /**
   * Elementos de acción en la esquina superior derecha
   */
  actions?: ReactNode
  /**
   * Clases personalizadas adicionales
   */
  className?: string
  /**
   * Indica si se oculta el botón de sidebar toggle si la vista ya lo incluye
   */
  hideSidebarToggle?: boolean
}

export const PageHeader = ({
  title,
  actions,
  className = '',
  hideSidebarToggle = false,
}: PageHeaderProps) => {
  const { isCollapsed, toggleSidebar } = useSidebar()

  return (
    <header
      className={`flex items-center justify-between border-b border-slate-200/80 bg-white/60 px-4 py-3 backdrop-blur-md shrink-0 rounded-2xl mb-6 shadow-2xs ${className}`}
    >
      <div className="flex items-center gap-3 min-w-0">
        {!hideSidebarToggle && (
          <button
            type="button"
            onClick={toggleSidebar}
            className="flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition shadow-2xs cursor-pointer shrink-0"
            title={isCollapsed ? 'Expandir menú lateral' : 'Colapsar menú lateral'}
            aria-label={isCollapsed ? 'Expandir menú lateral' : 'Colapsar menú lateral'}
          >
            {isCollapsed ? (
              <PanelLeftOpen className="h-4 w-4" />
            ) : (
              <PanelLeftClose className="h-4 w-4" />
            )}
          </button>
        )}

        <div className="flex items-center gap-2">
          <span className="text-slate-300 font-light text-sm" aria-hidden>
            |
          </span>
          <h1 className="text-sm md:text-base font-bold text-slate-800 tracking-tight truncate">
            {title}
          </h1>
        </div>
      </div>

      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </header>
  )
}

export default PageHeader

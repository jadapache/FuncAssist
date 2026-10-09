import type { ReactNode } from 'react'

interface PageHeaderProps {
  /**
   * Supertítulo / Eyebrow (e.g. "MÓDULO FUNCIONAL", "SISTEMA RAG & INDEXACIÓN")
   */
  eyebrow?: string
  /**
   * Insignia / Badge opcional al lado del eyebrow (e.g. "IA + Whisper")
   */
  badge?: ReactNode
  /**
   * Título principal de la página (h1)
   */
  title: string
  /**
   * Subtítulo / Descripción
   */
  subtitle?: string | ReactNode
  /**
   * Elementos de acción en la esquina superior derecha (e.g. botones de acción primaria o configuración)
   */
  actions?: ReactNode
  /**
   * Clases personalizadas adicionales
   */
  className?: string
}

export const PageHeader = ({
  eyebrow,
  badge,
  title,
  subtitle,
  actions,
  className = '',
}: PageHeaderProps) => {
  return (
    <header className={`flex flex-col md:flex-row md:items-start justify-between gap-4 ${className}`}>
      <div className="space-y-1">
        {(eyebrow || badge) && (
          <div className="flex items-center gap-2">
            {eyebrow && (
              <p className="text-xs font-bold uppercase tracking-widest text-[#002777]">
                {eyebrow}
              </p>
            )}
            {badge}
          </div>
        )}
        <h1 className="page-title mt-0.5">{title}</h1>
        {subtitle && (
          <p className="page-subtitle max-w-3xl leading-relaxed">
            {subtitle}
          </p>
        )}
      </div>

      {actions && (
        <div className="flex items-center gap-2 shrink-0 pt-1 md:pt-0">
          {actions}
        </div>
      )}
    </header>
  )
}

export default PageHeader

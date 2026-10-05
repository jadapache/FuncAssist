import React from 'react'
import { Loader2, Sparkles, Copy, Check, RefreshCw } from 'lucide-react'
import { DownloadMenu } from './DownloadMenu'

interface SummaryPanelProps {
  summaryParagraphs: string[]
  keyInsights: string[]
  isSummaryReady: boolean
  isGeneratingSummary: boolean
  isJobActive: boolean
  hasCopiedSummary: boolean
  showSummaryDownloadMenu: boolean
  summaryMenuRef: React.RefObject<HTMLDivElement | null>
  onToggleDownloadMenu: () => void
  onGenerateSummary: () => void
  onCopySummary: () => void
  onDownloadTxt: () => void
  onDownloadJson: () => void
}

export const SummaryPanel: React.FC<SummaryPanelProps> = ({
  summaryParagraphs,
  keyInsights,
  isSummaryReady,
  isGeneratingSummary,
  isJobActive,
  hasCopiedSummary,
  showSummaryDownloadMenu,
  summaryMenuRef,
  onToggleDownloadMenu,
  onGenerateSummary,
  onCopySummary,
  onDownloadTxt,
  onDownloadJson,
}) => {
  const downloadItems = [
    {
      label: 'Texto (.txt)',
      description: 'Formato lectura limpia',
      icon: 'text' as const,
      color: 'blue' as const,
      onSelect: onDownloadTxt,
    },
    {
      label: 'Estructurado (.json)',
      description: 'Párrafos e insights',
      icon: 'text' as const,
      color: 'amber' as const,
      onSelect: onDownloadJson,
    },
  ]

  return (
    <aside className="w-full lg:w-[480px] xl:w-[540px] flex flex-col min-h-0 bg-white shrink-0">
      {/* Panel Header Toolbar */}
      <div className="h-11 px-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between shrink-0 shadow-2xs">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-100 text-amber-800">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <h2 className="text-xs font-bold text-slate-800 uppercase tracking-wide">Resumen</h2>
        </div>

        {/* Action Buttons: Copiar, Descargar, Regenerar */}
        <div className="flex items-center gap-2">
          {/* Copy Summary Button */}
          <button
            type="button"
            onClick={onCopySummary}
            disabled={!isSummaryReady}
            className="p-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 flex items-center justify-center"
            title={hasCopiedSummary ? 'Copiado al portapapeles' : 'Copiar resumen'}
          >
            {hasCopiedSummary ? (
              <Check className="h-3.5 w-3.5 text-emerald-600" />
            ) : (
              <Copy className="h-3.5 w-3.5 text-slate-500" />
            )}
          </button>

          {/* Download Summary Dropdown */}
          <DownloadMenu
            menuRef={summaryMenuRef}
            isOpen={showSummaryDownloadMenu}
            onToggle={onToggleDownloadMenu}
            items={downloadItems}
            disabled={!isSummaryReady}
            title="Descargar resumen"
          />

          {/* Regenerate Summary Button */}
          {isSummaryReady && (
            <button
              type="button"
              onClick={onGenerateSummary}
              disabled={isGeneratingSummary}
              className="p-1.5 bg-white hover:bg-slate-100 text-slate-600 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 flex items-center justify-center"
              title="Regenerar resumen con IA"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isGeneratingSummary ? 'animate-spin text-[#002777]' : ''}`} />
            </button>
          )}
        </div>
      </div>

      {/* Panel Body: Clean Reading View matching reference image */}
      <div className="flex-1 min-h-0 overflow-y-auto p-6 sm:p-8 bg-white space-y-6">
        {isGeneratingSummary ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-3 text-slate-400">
            <Loader2 className="h-8 w-8 animate-spin text-[#002777]" />
            <p className="text-xs font-semibold text-slate-700">
              Generando resumen ejecutivo con IA...
            </p>
            <p className="text-[11px] text-slate-400 max-w-xs">
              Extrayendo contexto, acuerdos clave y puntos destacados de la reunión.
            </p>
          </div>
        ) : isSummaryReady ? (
          <div className="space-y-6 animate-fade-in max-w-xl">
            {/* 1. Summary Section */}
            {summaryParagraphs.length > 0 && (
              <section className="space-y-4">
                <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">Summary</h2>
                <div className="space-y-4 text-sm text-slate-700 leading-relaxed font-normal">
                  {summaryParagraphs.map((paragraph, idx) => (
                    <p key={idx} className="leading-relaxed">
                      {paragraph}
                    </p>
                  ))}
                </div>
              </section>
            )}

            {/* 2. Key Insights Section */}
            {keyInsights.length > 0 && (
              <section className="space-y-3.5 pt-2">
                <h3 className="text-xl font-bold text-slate-900 tracking-tight">Key Insights</h3>
                <ul className="space-y-3">
                  {keyInsights.map((insight, idx) => (
                    <li
                      key={idx}
                      className="flex items-start gap-3 text-sm text-slate-700 leading-relaxed"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-slate-400 mt-2 shrink-0" />
                      <span>{insight}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-4 text-slate-400">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-50 text-amber-700 ring-1 ring-amber-100">
              <Sparkles className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <h4 className="text-sm font-bold text-slate-800">Resumen no generado</h4>
              <p className="text-xs text-slate-500 max-w-xs">
                Genera una síntesis con IA para preparativos de los
                entregables funcionales.
              </p>
            </div>

            <button
              type="button"
              onClick={onGenerateSummary}
              disabled={isJobActive}
              className="inline-flex items-center gap-2 px-4 py-2 bg-[#002777] hover:bg-[#001e5c] text-white text-xs font-bold rounded-xl shadow-xs transition cursor-pointer disabled:opacity-40"
            >
              <Sparkles className="h-3.5 w-3.5 text-amber-300" />
              <span>Generar Resumen</span>
            </button>
          </div>
        )}
      </div>
    </aside>
  )
}

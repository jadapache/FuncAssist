import React from 'react'
import { Loader2, Sparkles, Copy, Check, RefreshCw } from 'lucide-react'
import { DownloadMenu } from './DownloadMenu'
import { MarkdownMessage } from '../../document/components/MarkdownMessage'

interface SummaryTemplateOption {
  id: string
  title: string
  description?: string
}

interface SummaryPanelProps {
  summaryText?: string | null
  summaryParagraphs: string[]
  keyInsights: string[]
  summaryTemplates?: SummaryTemplateOption[]
  selectedTemplate?: string
  onSelectTemplate?: (templateId: string) => void
  isSummaryReady: boolean
  isGeneratingSummary: boolean
  isJobActive: boolean
  hasTranscriptContent?: boolean
  hasCopiedSummary: boolean
  showSummaryDownloadMenu: boolean
  summaryMenuRef: React.RefObject<HTMLDivElement | null>
  onToggleDownloadMenu: () => void
  onGenerateSummary: () => void
  onCopySummary: () => void
  onDownloadMd: () => void
  onDownloadJson: () => void
}

export const SummaryPanel: React.FC<SummaryPanelProps> = ({
  summaryText,
  summaryParagraphs,
  keyInsights,
  summaryTemplates = [],
  selectedTemplate = '',
  onSelectTemplate,
  isSummaryReady,
  isGeneratingSummary,
  isJobActive,
  hasTranscriptContent = true,
  hasCopiedSummary,
  showSummaryDownloadMenu,
  summaryMenuRef,
  onToggleDownloadMenu,
  onGenerateSummary,
  onCopySummary,
  onDownloadMd,
  onDownloadJson,
}) => {
  const downloadItems = [
    {
      label: 'Texto (.md)',
      description: 'Formato Markdown limpio',
      icon: 'text' as const,
      color: 'blue' as const,
      onSelect: onDownloadMd,
    },
    {
      label: 'Estructurado (.json)',
      description: 'Párrafos e insights',
      icon: 'text' as const,
      color: 'amber' as const,
      onSelect: onDownloadJson,
    },
  ]

  const activeTemplateTitle =
    summaryTemplates.find((t) => t.id === selectedTemplate)?.title ||
    'Notas Estándar de Reunión'

  return (
    <aside className="w-full lg:w-[480px] xl:w-[540px] flex flex-col min-h-0 bg-white shrink-0">
      {/* Panel Header Toolbar */}
      <div className="h-11 px-3 sm:px-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between shrink-0 shadow-2xs gap-2">
        <div className="flex items-center gap-2 shrink-0">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-100 text-amber-800 shrink-0">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <h2 className="text-xs font-bold text-slate-800 uppercase tracking-wide shrink-0">
            Resumen
          </h2>
        </div>

        {/* Center: Template / Rubric Selector Dropdown */}
        {summaryTemplates.length > 0 && onSelectTemplate && (
          <div className="flex-1 flex justify-center px-1 sm:px-2 min-w-0">
            <label htmlFor="summary-template-select-header" className="sr-only">
              Plantilla de Resumen
            </label>
            <select
              id="summary-template-select-header"
              value={selectedTemplate}
              onChange={(e) => onSelectTemplate(e.target.value)}
              disabled={isGeneratingSummary || isJobActive}
              className="w-full max-w-[260px] sm:max-w-[320px] text-xs font-semibold bg-white border border-slate-300 rounded-lg px-2.5 py-1 text-slate-700 truncate shadow-2xs hover:border-slate-400 focus:outline-none focus:ring-1 focus:ring-[#002777] cursor-pointer disabled:opacity-50"
              title={`Plantilla actual: ${activeTemplateTitle}`}
            >
              {summaryTemplates.map((tmpl) => (
                <option key={tmpl.id} value={tmpl.id}>
                  {tmpl.title}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Action Buttons: Copiar, Descargar, Regenerar */}
        <div className="flex items-center gap-1.5 shrink-0">
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
              onClick={() => onGenerateSummary()}
              disabled={isGeneratingSummary}
              className="p-1.5 bg-white hover:bg-slate-100 text-slate-600 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 flex items-center justify-center"
              title={`Regenerar resumen con plantilla: ${activeTemplateTitle}`}
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${isGeneratingSummary ? 'animate-spin text-[#002777]' : ''}`}
              />
            </button>
          )}
        </div>
      </div>

      {/* Panel Body */}
      <div className="flex-1 min-h-0 overflow-y-auto p-6 sm:p-8 bg-white space-y-6">
        {isGeneratingSummary ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-3 text-slate-400">
            <Loader2 className="h-8 w-8 animate-spin text-[#002777]" />
            <p className="text-xs font-semibold text-slate-700">
              Generando resumen ejecutivo con IA...
            </p>
            <p className="text-[11px] text-slate-400 max-w-xs">
              Aplicando rúbrica de {activeTemplateTitle} a la transcripción.
            </p>
          </div>
        ) : isSummaryReady ? (
          <div className="space-y-6 animate-fade-in w-full">
            {summaryText ? (
              <MarkdownMessage content={summaryText} className="text-xs text-slate-700 w-full" />
            ) : (
              <>
                {summaryParagraphs.length > 0 && (
                  <section className="space-y-4">
                    <h2 className="text-sm font-bold text-slate-900 tracking-tight pb-1 border-b border-slate-100">
                      Resumen
                    </h2>
                    <div className="space-y-3 text-xs text-slate-700 leading-relaxed font-normal">
                      {summaryParagraphs.map((paragraph, idx) => (
                        <MarkdownMessage key={idx} content={paragraph} />
                      ))}
                    </div>
                  </section>
                )}

                {keyInsights.length > 0 && (
                  <section className="space-y-3.5 pt-2">
                    <h3 className="text-xs font-bold text-slate-900 tracking-tight">
                      Puntos Clave
                    </h3>
                    <ul className="space-y-2">
                      {keyInsights.map((insight, idx) => (
                        <li
                          key={idx}
                          className="flex items-start gap-2.5 text-xs text-slate-700 leading-relaxed"
                        >
                          <span className="h-1.5 w-1.5 rounded-full bg-slate-400 mt-1.5 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <MarkdownMessage content={insight} />
                          </div>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </>
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
                Selecciona una plantilla o rúbrica en la barra superior y genera una síntesis con IA para tus
                entregables.
              </p>
            </div>

            <button
              type="button"
              onClick={() => onGenerateSummary()}
              disabled={isJobActive || isGeneratingSummary || !hasTranscriptContent}
              className={`inline-flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl shadow-xs transition ${
                hasTranscriptContent && !isJobActive && !isGeneratingSummary
                  ? 'bg-[#002777] hover:bg-[#001e5c] text-white cursor-pointer'
                  : 'bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed opacity-60'
              }`}
              title={
                !hasTranscriptContent
                  ? 'Se requiere una transcripción con diálogos para generar el resumen'
                  : `Generar resumen usando plantilla: ${activeTemplateTitle}`
              }
            >
              <Sparkles
                className={`h-3.5 w-3.5 ${hasTranscriptContent && !isJobActive && !isGeneratingSummary ? 'text-amber-300' : 'text-slate-400'}`}
              />
              <span>Generar Resumen</span>
            </button>
          </div>
        )}
      </div>
    </aside>
  )
}

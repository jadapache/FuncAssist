/**
 * UniverErrorBoundary.tsx
 * Resilient React Error Boundary that prevents white-screen crashes in document and spreadsheet workspaces.
 */

import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw, Copy, Check, FileText } from 'lucide-react'

interface Props {
  children: ReactNode
  fallbackContent?: string
  onSwitchToCodeMode?: () => void
  onRecover?: () => void
}

interface State {
  hasError: boolean
  error: Error | null
  copied: boolean
}

export class UniverErrorBoundary extends Component<Props, State> {
  public override state: State = {
    hasError: false,
    error: null,
    copied: false,
  }

  public static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      error,
      copied: false,
    }
  }

  public override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('UniverContainer error caught by boundary:', error, errorInfo)
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null })
    this.props.onRecover?.()
  }

  private handleCopyFallback = () => {
    if (this.props.fallbackContent) {
      void navigator.clipboard.writeText(this.props.fallbackContent)
      this.setState({ copied: true })
      setTimeout(() => this.setState({ copied: false }), 2000)
    }
  }

  public override render() {
    if (this.state.hasError) {
      return (
        <div className="p-8 m-4 bg-white border border-red-200 rounded-2xl shadow-xl max-w-2xl mx-auto space-y-4 text-slate-800 animate-fadeIn font-sans">
          <div className="flex items-start gap-3.5">
            <div className="p-2.5 bg-red-100 text-red-700 rounded-xl shrink-0">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <h3 className="font-bold text-base text-slate-900">
                Se detectó una inconsistencia en la vista visual del documento
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                El componente visual previno un cierre inesperado. Tu contenido está totalmente a salvo y no se ha perdido información.
              </p>
            </div>
          </div>

          {this.state.error?.message ? (
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs font-mono text-slate-700 overflow-x-auto max-h-28">
              {this.state.error.message}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
            <button
              type="button"
              onClick={this.handleReset}
              className="px-3.5 py-1.5 bg-[#002777] hover:bg-[#003399] text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer shadow-xs"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Restaurar Vista Visual</span>
            </button>

            {this.props.onSwitchToCodeMode && (
              <button
                type="button"
                onClick={() => {
                  this.handleReset()
                  this.props.onSwitchToCodeMode?.()
                }}
                className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
              >
                <FileText className="h-3.5 w-3.5 text-[#002777]" />
                <span>Editar en Modo Código Markdown</span>
              </button>
            )}

            {this.props.fallbackContent && (
              <button
                type="button"
                onClick={this.handleCopyFallback}
                className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ml-auto"
              >
                {this.state.copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                <span>{this.state.copied ? '¡Copiado!' : 'Copiar Texto Respaldo'}</span>
              </button>
            )}
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

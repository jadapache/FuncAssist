/**
 * ErrorBoundary.tsx
 * Global error boundary for graceful error handling
 */

import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
  onError?: (error: Error, errorInfo: ErrorInfo) => void
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Error caught by ErrorBoundary:', error, errorInfo)
    this.props.onError?.(error, errorInfo)
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="min-h-screen flex items-center justify-center bg-slate-100 p-6">
          <div className="max-w-md w-full bg-white rounded-2xl shadow-xl border border-slate-200 p-8 space-y-4 animate-fade-in">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-red-100 text-red-600">
                <AlertTriangle className="h-6 w-6" />
              </div>
              <div>
                <h2 className="text-base font-bold text-slate-900">Ha ocurrido un error inesperado</h2>
                <p className="text-xs text-slate-500">Se detectó una excepción en la interfaz</p>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              La vista actual encontró un problema durante su ejecución. Puedes intentar restablecer el estado o recargar la página.
            </p>

            {this.state.error && (
              <details className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-xl p-3">
                <summary className="cursor-pointer font-semibold text-slate-700">Detalles técnicos</summary>
                <pre className="mt-2 text-[11px] overflow-auto whitespace-pre-wrap font-mono text-red-700">
                  {this.state.error.message}
                </pre>
              </details>
            )}

            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={this.handleReset}
                className="flex-1 px-4 py-2 bg-[#002777] hover:bg-[#001e5c] text-white rounded-xl text-xs font-bold transition shadow-xs cursor-pointer"
              >
                Reintentar
              </button>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="flex-1 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition border border-slate-200 cursor-pointer"
              >
                Recargar página
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

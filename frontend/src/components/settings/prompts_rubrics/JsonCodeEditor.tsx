import { AlertTriangle, FileCode } from 'lucide-react'

interface JsonCodeEditorProps {
  rawJsonText: string
  jsonError: string | null
  onChange: (text: string) => void
}

export const JsonCodeEditor = ({ rawJsonText, jsonError, onChange }: JsonCodeEditorProps) => {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-500 font-medium flex items-center gap-1.5">
          <FileCode className="h-3.5 w-3.5 text-[#002777]" />
          <span>Edición directa del archivo fuente JSON</span>
        </span>
        <span className="text-[11px] text-slate-400 font-mono">
          {rawJsonText.split('\n').length} líneas
        </span>
      </div>

      {jsonError && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
          <div>
            <strong className="block font-bold">Error en la sintaxis del JSON:</strong>
            <span className="font-mono text-[11px]">{jsonError}</span>
          </div>
        </div>
      )}

      <textarea
        rows={16}
        value={rawJsonText}
        onChange={(e) => onChange(e.target.value)}
        className={[
          'w-full p-4 font-mono text-xs rounded-xl border leading-relaxed resize-y focus:outline-none focus:ring-2 shadow-inner',
          jsonError
            ? 'border-red-300 bg-red-50/20 focus:ring-red-500 text-red-900'
            : 'border-slate-300 bg-slate-900 text-emerald-400 focus:ring-[#002777]',
        ].join(' ')}
        spellCheck={false}
      />
    </div>
  )
}

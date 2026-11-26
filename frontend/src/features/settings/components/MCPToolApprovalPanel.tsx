import { useState } from 'react'
import { ShieldCheck, Ban } from 'lucide-react'
import type { McpAdminServer, McpToolApprovalInput } from '../types'
import { buildToolApproval, buildToolRevocation } from '../utils/mcpTools'

export interface MCPToolApprovalPanelProps {
  server: McpAdminServer
  disabled: boolean
  onSetTools: (id: string, tools: McpToolApprovalInput[]) => Promise<boolean>
}

const inputClass =
  'w-full px-3 py-2 text-xs text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100'

export const MCPToolApprovalPanel = ({ server, disabled, onSetTools }: MCPToolApprovalPanelProps) => {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [inputSchema, setInputSchema] = useState('')
  const [readOnly, setReadOnly] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const handleApprove = async () => {
    const result = buildToolApproval({ name, description, inputSchema, readOnly })
    if (!result.ok) {
      setFormError(result.error)
      return
    }
    setFormError(null)
    const saved = await onSetTools(server.id, [result.tool])
    if (!saved) return
    setName('')
    setDescription('')
    setInputSchema('')
    setReadOnly(false)
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-4">
      <div className="space-y-1">
        <h5 className="text-xs font-bold text-slate-900">Herramientas aprobadas</h5>
        <p className="text-[11px] text-slate-500">
          Cada herramienta aprobada queda fijada a la descripción y el esquema revisados. Si el servidor los cambia, habrá que aprobarla de nuevo.
        </p>
      </div>

      {server.tools.length === 0 ? (
        <p className="text-xs text-slate-500">Este servidor aún no tiene herramientas registradas.</p>
      ) : (
        <ul className="space-y-2">
          {server.tools.map((tool) => (
            <li
              key={tool.name}
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2"
            >
              <div className="flex items-center gap-2 flex-wrap min-w-0">
                <span className="text-xs font-mono font-semibold text-slate-900">{tool.name}</span>
                {tool.approved ? (
                  <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                    Aprobada
                  </span>
                ) : (
                  <span className="text-[11px] font-medium text-slate-500 bg-slate-200 border border-slate-300 px-2 py-0.5 rounded-full">
                    Sin aprobar
                  </span>
                )}
                <span className="text-[11px] text-slate-500">
                  {tool.read_only ? 'Solo lectura' : 'Requiere confirmación'}
                </span>
                {tool.approved && tool.approved_by && (
                  <span className="text-[11px] text-slate-400">por {tool.approved_by}</span>
                )}
              </div>
              {tool.approved && (
                <button
                  type="button"
                  onClick={() => void onSetTools(server.id, [buildToolRevocation(tool.name)])}
                  disabled={disabled}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 text-red-600 hover:bg-red-50 text-xs font-semibold cursor-pointer transition disabled:opacity-50 self-start sm:self-auto"
                >
                  <Ban className="h-3.5 w-3.5" />
                  <span>Revocar</span>
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="border-t border-slate-100 pt-4 space-y-3">
        <h5 className="text-xs font-bold text-slate-900">Aprobar herramienta</h5>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-semibold text-slate-700 block mb-1">Nombre *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="search_docs"
              className={`${inputClass} font-mono`}
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-700 block mb-1">Descripción</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Busca documentos por texto"
              className={inputClass}
            />
          </div>
          <div className="sm:col-span-2">
            <label className="text-xs font-semibold text-slate-700 block mb-1">
              Esquema de entrada (JSON, opcional)
            </label>
            <textarea
              value={inputSchema}
              onChange={(e) => setInputSchema(e.target.value)}
              rows={4}
              placeholder='{"type": "object", "properties": {}}'
              className={`${inputClass} font-mono`}
            />
          </div>
        </div>

        <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
          <input
            type="checkbox"
            checked={readOnly}
            onChange={(e) => setReadOnly(e.target.checked)}
            className="h-4 w-4 rounded border-slate-300"
          />
          <span>Solo lectura (si no se marca, cada ejecución requerirá confirmación del usuario)</span>
        </label>

        {formError && <p className="text-xs text-red-600">{formError}</p>}

        <button
          type="button"
          onClick={() => void handleApprove()}
          disabled={disabled || !name.trim()}
          className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold disabled:opacity-50 cursor-pointer shadow-xs transition flex items-center gap-1.5"
        >
          <ShieldCheck className="h-4 w-4" />
          <span>Aprobar herramienta</span>
        </button>
      </div>
    </div>
  )
}

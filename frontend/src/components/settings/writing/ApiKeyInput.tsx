import { Eye, EyeOff, Key } from 'lucide-react'

export interface ApiKeyInputProps {
  label: string
  value: string
  onChange: (val: string) => void
  showKey: boolean
  setShowKey: (show: boolean) => void
  hasSavedKey?: boolean
  placeholder?: string
}

export const ApiKeyInput = ({
  label,
  value,
  onChange,
  showKey,
  setShowKey,
  hasSavedKey,
  placeholder = 'sk-...',
}: ApiKeyInputProps) => {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-bold text-slate-800 flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <Key className="h-3.5 w-3.5 text-[#002777]" />
          <span>{label}</span>
        </span>
        {hasSavedKey && !value && (
          <span className="text-[10px] text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full font-semibold">
            ✓ Clave guardada en servidor
          </span>
        )}
      </label>
      <div className="relative">
        <input
          type={showKey ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={hasSavedKey ? '•••••••••••••••• (Deja en blanco para conservar)' : placeholder}
          className="input-field text-xs font-mono py-2 pr-10 border border-slate-200 rounded-xl w-full"
        />
        <button
          type="button"
          onClick={() => setShowKey(!showKey)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-1 cursor-pointer"
        >
          {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
        </button>
      </div>
    </div>
  )
}


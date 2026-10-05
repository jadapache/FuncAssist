import React from 'react'
import { Download, ChevronDown, FileText } from 'lucide-react'

interface DownloadItem {
  label: string
  description: string
  icon: 'text' | 'json'
  color: 'blue' | 'amber'
  onSelect: () => void
}

interface DownloadMenuProps {
  menuRef: React.RefObject<HTMLDivElement | null>
  isOpen: boolean
  onToggle: () => void
  items: DownloadItem[]
  disabled?: boolean
  title?: string
}

export const DownloadMenu: React.FC<DownloadMenuProps> = ({
  menuRef,
  isOpen,
  onToggle,
  items,
  disabled = false,
  title = 'Descargar',
}) => {
  const colorMap = {
    blue: 'text-blue-600',
    amber: 'text-amber-600',
  }

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={onToggle}
        disabled={disabled}
        className="p-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl transition shadow-2xs cursor-pointer disabled:opacity-40 flex items-center gap-0.5"
        title={title}
      >
        <Download className="h-3.5 w-3.5 text-slate-500" />
        <ChevronDown className="h-3 w-3 text-slate-400" />
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-1.5 w-44 bg-white border border-slate-200 rounded-xl shadow-xl py-1 z-30 animate-scale-in">
          {items.map((item, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => {
                item.onSelect()
              }}
              className="w-full px-3 py-2 text-left text-xs text-slate-700 hover:bg-blue-50 hover:text-[#002777] flex items-center gap-2 transition cursor-pointer"
            >
              <FileText className={`h-3.5 w-3.5 ${colorMap[item.color]}`} />
              <div>
                <div className="font-bold">{item.label}</div>
                <div className="text-[10px] text-slate-400">{item.description}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

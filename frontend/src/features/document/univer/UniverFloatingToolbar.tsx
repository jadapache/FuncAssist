/**
 * UniverFloatingToolbar.tsx
 * Ultra-Responsive Floating WYSIWYG Toolbar for Univer Container.
 * Features rounded-full pill container with px-4 framing to completely prevent icon clipping at curved ends.
 */

import React, { useEffect, useRef, useState } from 'react'
import {
  Undo2,
  Redo2,
  ChevronDown,
  Minus,
  Plus,
  Bold,
  Italic,
  Underline,
  AlignLeft,
  AlignCenter,
  AlignRight,
  AlignJustify,
  List,
  ListOrdered,
  Indent,
  Outdent,
  Type,
  MoreVertical,
} from 'lucide-react'

export interface UniverFloatingToolbarProps {
  zoom: number
  onZoomChange: (zoom: number) => void
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
  textStyle: string
  onTextStyleChange: (style: string) => void
  fontFamily: string
  onFontFamilyChange: (font: string) => void
  fontSize: number
  onFontSizeChange: (size: number) => void
  isBold: boolean
  onToggleBold: () => void
  isItalic: boolean
  onToggleItalic: () => void
  isUnderline: boolean
  onToggleUnderline: () => void
  textColor: string
  onTextColorChange: (color: string) => void
  alignment: 'left' | 'center' | 'right' | 'justify'
  onAlignmentChange: (align: 'left' | 'center' | 'right' | 'justify') => void
  onToggleBulletList: () => void
  onToggleNumberedList: () => void
  onIndent: () => void
  onOutdent: () => void
  mode?: 'template' | 'artifact'
}

const TEXT_COLORS = [
  { label: 'Azul Corporativo', value: '#002777' },
  { label: 'Negro Slate', value: '#0f172a' },
  { label: 'Gris Oscuro', value: '#334155' },
  { label: 'Azul Marino', value: '#1e3a8a' },
  { label: 'Verde Esmeralda', value: '#047857' },
  { label: 'Rojo Carmín', value: '#b91c1c' },
  { label: 'Púrpura', value: '#6b21a8' },
]

export const UniverFloatingToolbar: React.FC<UniverFloatingToolbarProps> = ({
  zoom,
  onZoomChange,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  textStyle,
  onTextStyleChange,
  fontFamily,
  onFontFamilyChange,
  fontSize,
  onFontSizeChange,
  isBold,
  onToggleBold,
  isItalic,
  onToggleItalic,
  isUnderline,
  onToggleUnderline,
  textColor,
  onTextColorChange,
  alignment,
  onAlignmentChange,
  onToggleBulletList,
  onToggleNumberedList,
  onIndent,
  onOutdent,
}) => {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState<number>(800)
  const [showColorPicker, setShowColorPicker] = useState(false)
  const [showAlignPicker, setShowAlignPicker] = useState(false)
  const [showMoreMenu, setShowMoreMenu] = useState(false)

  // Measure actual container pixel width via ResizeObserver (measures parent canvas viewport width)
  useEffect(() => {
    if (!wrapperRef.current) return

    const parentEl = wrapperRef.current.parentElement || wrapperRef.current

    const updateWidth = () => {
      const measured = parentEl.clientWidth || parentEl.offsetWidth || 800
      setContainerWidth(measured)
    }

    updateWidth()

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect && entry.contentRect.width > 0) {
          setContainerWidth(entry.contentRect.width)
        }
      }
    })

    observer.observe(parentEl)
    return () => observer.disconnect()
  }, [])

  // Responsive container width tiers:
  const isXl = containerWidth >= 760
  const isLg = containerWidth >= 620
  const isMd = containerWidth >= 500
  const isSm = containerWidth >= 440

  const AlignIcon =
    alignment === 'center'
      ? AlignCenter
      : alignment === 'right'
        ? AlignRight
        : alignment === 'justify'
          ? AlignJustify
          : AlignLeft

  return (
    <div ref={wrapperRef} className="w-full flex flex-col items-center gap-1 select-none my-0.5 transition-all">
      {/* 1. DYNAMIC PRIMARY FLOATING TOOLBAR */}
      <div className="relative z-20 bg-white/95 backdrop-blur-md border border-slate-300/90 shadow-lg rounded-full px-2.5 py-0.5 flex items-center justify-center gap-0.5 text-slate-700 h-9 shrink-0 max-w-full">
        {/* 1. Zoom Selector (First element on the left) */}
        <div className="flex items-center shrink-0">
          <select
            value={zoom}
            onChange={(e) => onZoomChange(Number(e.target.value))}
            className="h-7.5 bg-transparent hover:bg-slate-100 text-xs font-semibold px-0.5 rounded-md border-0 focus:outline-hidden cursor-pointer text-slate-700"
            title="Zoom de página"
          >
            <option value={50}>50%</option>
            <option value={75}>75%</option>
            <option value={100}>100%</option>
            <option value={125}>125%</option>
            <option value={150}>150%</option>
          </select>
        </div>

        <div className="h-4 w-px bg-slate-200 mx-0.5 shrink-0" />

        {/* Deshacer / Rehacer */}
        <button
          type="button"
          onClick={onUndo}
          disabled={!canUndo}
          className="h-7.5 w-6 rounded-full hover:bg-slate-100 disabled:opacity-30 disabled:hover:bg-transparent text-slate-700 flex items-center justify-center transition cursor-pointer shrink-0"
          title="Deshacer (Ctrl+Z)"
        >
          <Undo2 className="h-3.5 w-3.5" />
        </button>

        <button
          type="button"
          onClick={onRedo}
          disabled={!canRedo}
          className="h-7.5 w-6 rounded-full hover:bg-slate-100 disabled:opacity-30 disabled:hover:bg-transparent text-slate-700 flex items-center justify-center transition cursor-pointer shrink-0"
          title="Rehacer (Ctrl+Y)"
        >
          <Redo2 className="h-3.5 w-3.5" />
        </button>

        <div className="h-4 w-px bg-slate-200 mx-0.5 shrink-0" />

        {/* Text Style Dropdown */}
        <div className="relative shrink-0">
          <select
            value={textStyle}
            onChange={(e) => onTextStyleChange(e.target.value)}
            className={`h-7.5 bg-transparent hover:bg-slate-100 text-xs font-bold text-[#002777] px-0.5 rounded-md border-0 focus:outline-hidden cursor-pointer truncate transition-all ${isXl ? 'w-[84px]' : isLg ? 'w-[76px]' : isMd ? 'w-[68px]' : isSm ? 'w-[60px]' : 'w-[52px]'
              }`}
          >
            <option value="paragraph">Normal</option>
            <option value="h1">Título</option>
            <option value="h2">Subtítulo</option>
          </select>
        </div>

        {/* Font Family Dropdown */}
        <div className="h-4 w-px bg-slate-200 mx-0.5 shrink-0" />
        <div className="relative shrink-0">
          <select
            value={fontFamily}
            onChange={(e) => onFontFamilyChange(e.target.value)}
            className={`h-7.5 bg-transparent hover:bg-slate-100 text-xs font-semibold px-0.5 rounded-md border-0 focus:outline-hidden cursor-pointer truncate transition-all ${isXl ? 'w-[76px]' : isLg ? 'w-[68px]' : isMd ? 'w-[60px]' : isSm ? 'w-[52px]' : 'w-[44px]'
              }`}
            title="Fuente"
          >
            <option value="Arial">Arial</option>
            <option value="Inter">Inter</option>
            <option value="Roboto">Roboto</option>
            <option value="Times New Roman">Times</option>
            <option value="Courier New">Courier</option>
            <option value="Georgia">Georgia</option>
          </select>
        </div>

        {/* Font Size Selector (- 13 +) (Visible if width >= 500px) */}
        {isMd && (
          <>
            <div className="h-4 w-px bg-slate-200 mx-0.5 shrink-0" />
            <div className="flex items-center h-7.5 shrink-0">
              <button
                type="button"
                onClick={() => onFontSizeChange(Math.max(8, fontSize - 1))}
                className="h-7.5 w-4 hover:bg-slate-100 rounded text-slate-600 flex items-center justify-center cursor-pointer"
                title="Disminuir tamaño"
              >
                <Minus className="h-3 w-3" />
              </button>
              <span className="w-5 text-center font-mono text-xs font-bold text-slate-800">
                {fontSize}
              </span>
              <button
                type="button"
                onClick={() => onFontSizeChange(Math.min(36, fontSize + 1))}
                className="h-7.5 w-4 hover:bg-slate-100 rounded text-slate-600 flex items-center justify-center cursor-pointer"
                title="Aumentar tamaño"
              >
                <Plus className="h-3 w-3" />
              </button>
            </div>
          </>
        )}

        <div className="h-4 w-px bg-slate-200 mx-0.5 shrink-0" />

        {/* Bold, Italic & Underline Buttons */}
        <div className="flex items-center gap-0.5 shrink-0">
          <button
            type="button"
            onClick={onToggleBold}
            className={`h-7.5 w-5.5 rounded-md font-bold text-xs flex items-center justify-center transition cursor-pointer shrink-0 ${isBold ? 'bg-blue-100 text-[#002777]' : 'text-slate-700 hover:bg-slate-100'
              }`}
            title="Negrita (Ctrl+B)"
          >
            <Bold className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            onClick={onToggleItalic}
            className={`h-7.5 w-5.5 rounded-md italic text-xs flex items-center justify-center transition cursor-pointer shrink-0 ${isItalic ? 'bg-blue-100 text-[#002777]' : 'text-slate-700 hover:bg-slate-100'
              }`}
            title="Cursiva (Ctrl+I)"
          >
            <Italic className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            onClick={onToggleUnderline}
            className={`h-7.5 w-5.5 rounded-md underline text-xs flex items-center justify-center transition cursor-pointer shrink-0 ${isUnderline ? 'bg-blue-100 text-[#002777]' : 'text-slate-700 hover:bg-slate-100'
              }`}
            title="Subrayado (Ctrl+U)"
          >
            <Underline className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="h-4 w-px bg-slate-200 mx-0.5 shrink-0" />

        {/* Color de Texto */}
        <div className="relative shrink-0">
          <button
            type="button"
            onClick={() => {
              setShowColorPicker(!showColorPicker)
              setShowAlignPicker(false)
            }}
            className={`h-7.5 w-5.5 rounded-md flex flex-col items-center justify-center transition cursor-pointer shrink-0 ${showColorPicker ? 'bg-blue-100 text-[#002777]' : 'text-slate-700 hover:bg-slate-100'
              }`}
            title="Color de texto"
          >
            <Type className="h-3.5 w-3.5" />
            <div className="h-0.5 w-3 rounded-full mt-0.5" style={{ backgroundColor: textColor }} />
          </button>

          {showColorPicker && (
            <div className="absolute right-0 top-full mt-1 bg-white border border-slate-200 rounded-xl shadow-xl p-2 z-50 flex flex-col gap-1 w-44">
              <span className="text-[10px] font-bold text-slate-400 uppercase px-1">
                Color de texto
              </span>
              {TEXT_COLORS.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => {
                    onTextColorChange(c.value)
                    setShowColorPicker(false)
                  }}
                  className="flex items-center gap-2 px-2 py-1 rounded text-xs hover:bg-slate-50 cursor-pointer"
                >
                  <div className="h-3.5 w-3.5 rounded-full border border-slate-300" style={{ backgroundColor: c.value }} />
                  <span className="text-slate-700 font-medium text-xs">{c.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Grouped Alignment Dropdown (Visible on primary bar if width >= 440px) */}
        {isSm && (
          <>
            <div className="h-4 w-px bg-slate-200 mx-0.5 shrink-0" />
            <div className="relative shrink-0">
              <button
                type="button"
                onClick={() => {
                  setShowAlignPicker(!showAlignPicker)
                  setShowColorPicker(false)
                }}
                className={`h-7.5 px-1 rounded-lg transition cursor-pointer flex items-center gap-0.5 ${showAlignPicker ? 'bg-blue-100 text-[#002777]' : 'hover:bg-slate-100 text-slate-700'
                  }`}
                title="Alineación de texto"
              >
                <AlignIcon className="h-3.5 w-3.5" />
                <ChevronDown className="h-3 w-3 text-slate-500" />
              </button>

              {showAlignPicker && (
                <div className="absolute left-1/2 -translate-x-1/2 top-full mt-1 bg-white border border-slate-200 rounded-xl shadow-xl p-1 z-50 flex flex-col gap-0.5 w-11 items-center">
                  <button
                    type="button"
                    onClick={() => {
                      onAlignmentChange('left')
                      setShowAlignPicker(false)
                    }}
                    className={`p-1.5 rounded-lg hover:bg-slate-100 transition cursor-pointer w-full flex justify-center ${alignment === 'left' ? 'bg-blue-100 text-[#002777]' : 'text-slate-700'
                      }`}
                    title="Alinear a la izquierda"
                  >
                    <AlignLeft className="h-4 w-4" />
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      onAlignmentChange('center')
                      setShowAlignPicker(false)
                    }}
                    className={`p-1.5 rounded-lg hover:bg-slate-100 transition cursor-pointer w-full flex justify-center ${alignment === 'center' ? 'bg-blue-100 text-[#002777]' : 'text-slate-700'
                      }`}
                    title="Centrar"
                  >
                    <AlignCenter className="h-4 w-4" />
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      onAlignmentChange('right')
                      setShowAlignPicker(false)
                    }}
                    className={`p-1.5 rounded-lg hover:bg-slate-100 transition cursor-pointer w-full flex justify-center ${alignment === 'right' ? 'bg-blue-100 text-[#002777]' : 'text-slate-700'
                      }`}
                    title="Alinear a la derecha"
                  >
                    <AlignRight className="h-4 w-4" />
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      onAlignmentChange('justify')
                      setShowAlignPicker(false)
                    }}
                    className={`p-1.5 rounded-lg hover:bg-slate-100 transition cursor-pointer w-full flex justify-center ${alignment === 'justify' ? 'bg-blue-100 text-[#002777]' : 'text-slate-700'
                      }`}
                    title="Justificar"
                  >
                    <AlignJustify className="h-4 w-4" />
                  </button>
                </div>
              )}
            </div>
          </>
        )}

        {/* Lists (Visible on primary bar if width >= 680px) */}
        {isXl && (
          <>
            <div className="h-4 w-px bg-slate-200 mx-0.5 shrink-0" />
            <div className="flex items-center gap-0.5 shrink-0">
              <button
                type="button"
                onClick={onToggleBulletList}
                className="h-7.5 w-7 rounded-md hover:bg-slate-100 text-slate-600 flex items-center justify-center transition cursor-pointer"
                title="Lista de viñetas"
              >
                <List className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={onToggleNumberedList}
                className="h-7.5 w-7 rounded-md hover:bg-slate-100 text-slate-600 flex items-center justify-center transition cursor-pointer"
                title="Lista numerada"
              >
                <ListOrdered className="h-3.5 w-3.5" />
              </button>
            </div>
          </>
        )}

        <div className="h-4 w-px bg-slate-200 mx-0.5 shrink-0" />

        {/* 3-DOTS MORE OPTIONS BUTTON */}
        <button
          type="button"
          onClick={() => setShowMoreMenu(!showMoreMenu)}
          className={`h-7.5 w-7.5 rounded-full transition cursor-pointer flex items-center justify-center shrink-0 ${showMoreMenu ? 'bg-blue-100 text-[#002777]' : 'hover:bg-slate-100 text-slate-700'
            }`}
          title="Más opciones de formato"
        >
          <MoreVertical className="h-4 w-4" />
        </button>
      </div>

      {/* 2. DYNAMIC HORIZONTAL SUB-TOOLBAR EXTENSION BAR (Shows items moved from primary bar + indents & zoom) */}
      {showMoreMenu && (
        <div className="relative z-10 bg-white/95 backdrop-blur-md border border-slate-300/90 shadow-lg rounded-full px-3 py-0.5 flex flex-wrap items-center justify-center gap-1 min-h-9 max-w-full text-slate-700 shrink-0 animate-fadeIn transition-all">
          {/* Alignment (Moved to 3-dots if width < 440px) */}
          {!isSm && (
            <>
              <div className="relative shrink-0">
                <button
                  type="button"
                  onClick={() => setShowAlignPicker(!showAlignPicker)}
                  className={`h-7.5 px-1.5 rounded-lg transition cursor-pointer flex items-center gap-0.5 ${showAlignPicker ? 'bg-blue-100 text-[#002777]' : 'hover:bg-slate-100 text-slate-700'
                    }`}
                  title="Alineación de texto"
                >
                  <AlignIcon className="h-3.5 w-3.5" />
                  <ChevronDown className="h-3 w-3 text-slate-500" />
                </button>
              </div>
              <div className="h-4 w-px bg-slate-200 mx-0.5 shrink-0" />
            </>
          )}

          {/* Font Size Selector (Moved to 3-dots if width < 500px) */}
          {!isMd && (
            <>
              <div className="flex items-center h-7.5 shrink-0">
                <button
                  type="button"
                  onClick={() => onFontSizeChange(Math.max(8, fontSize - 1))}
                  className="h-7.5 w-4 hover:bg-slate-100 rounded text-slate-600 flex items-center justify-center cursor-pointer"
                  title="Disminuir tamaño"
                >
                  <Minus className="h-3 w-3" />
                </button>
                <span className="w-5 text-center font-mono text-xs font-bold text-slate-800">
                  {fontSize}
                </span>
                <button
                  type="button"
                  onClick={() => onFontSizeChange(Math.min(36, fontSize + 1))}
                  className="h-7.5 w-4 hover:bg-slate-100 rounded text-slate-600 flex items-center justify-center cursor-pointer"
                  title="Aumentar tamaño"
                >
                  <Plus className="h-3 w-3" />
                </button>
              </div>
              <div className="h-4 w-px bg-slate-200 mx-0.5 shrink-0" />
            </>
          )}

          {/* Listas (Moved to 3-dots if width < 720px) */}
          {!isXl && (
            <>
              <div className="flex items-center gap-0.5 shrink-0">
                <button
                  type="button"
                  onClick={onToggleBulletList}
                  className="h-7.5 w-7 rounded-md hover:bg-slate-100 text-slate-600 flex items-center justify-center transition cursor-pointer"
                  title="Lista de viñetas"
                >
                  <List className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={onToggleNumberedList}
                  className="h-7.5 w-7 rounded-md hover:bg-slate-100 text-slate-600 flex items-center justify-center transition cursor-pointer"
                  title="Lista numerada"
                >
                  <ListOrdered className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="h-4 w-px bg-slate-200 mx-0.5 shrink-0" />
            </>
          )}

          {/* Sangría (Always in 3-dots) */}
          <div className="flex items-center gap-0.5 shrink-0">
            <button
              type="button"
              onClick={onOutdent}
              className="h-7.5 w-7 rounded-md hover:bg-slate-100 text-slate-600 flex items-center justify-center transition cursor-pointer"
              title="Disminuir sangría"
            >
              <Outdent className="h-3.5 w-3.5" />
            </button>

            <button
              type="button"
              onClick={onIndent}
              className="h-7.5 w-7 rounded-md hover:bg-slate-100 text-slate-600 flex items-center justify-center transition cursor-pointer"
              title="Aumentar sangría"
            >
              <Indent className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}


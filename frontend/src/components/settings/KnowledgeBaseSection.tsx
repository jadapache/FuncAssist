import { useEffect, useState } from 'react'
import {
  Database,
  FolderSync,
  HardDrive,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  FileDown,
  ShieldCheck,
  Folder,
} from 'lucide-react'
import { api, type KnowledgeIntegrityResponse } from '../../api/client'
import { useToast } from '../../context/ToastContext'

export const KnowledgeBaseSection = () => {
  const [configuredPath, setConfiguredPath] = useState('')
  const [resolvedPath, setResolvedPath] = useState('')
  const [isCustom, setIsCustom] = useState(false)
  const [isAccessible, setIsAccessible] = useState(true)
  const [inputPath, setInputPath] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  // Recovery tools state
  const [integrityLoading, setIntegrityLoading] = useState(false)
  const [integrityResult, setIntegrityResult] = useState<KnowledgeIntegrityResponse | null>(null)
  const [rebuildingIndex, setRebuildingIndex] = useState(false)
  const [exportingBackup, setExportingBackup] = useState(false)

  const { toast } = useToast()

  const loadPathInfo = async () => {
    setIsLoading(true)
    try {
      const res = await api.getKnowledgePath()
      setConfiguredPath(res.configured_path || '')
      setResolvedPath(res.resolved_path || '')
      setIsCustom(!!res.is_custom)
      setIsAccessible(res.is_accessible !== false)
      setInputPath(res.configured_path || '')
    } catch {
      toast.error('No se pudo obtener la ruta de la base de conocimiento.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    void loadPathInfo()
  }, [])

  const handleSave = async (pathToSave?: string) => {
    const val = (pathToSave !== undefined ? pathToSave : inputPath).trim()
    setIsSaving(true)
    try {
      const res = await api.setKnowledgePath(val)
      setConfiguredPath(res.configured_path || '')
      setResolvedPath(res.resolved_path || '')
      setIsCustom(!!res.is_custom)
      setIsAccessible(res.is_accessible !== false)
      setInputPath(res.configured_path || '')
      toast.success('Ruta de la Base de Conocimiento actualizada.')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al actualizar la ruta.')
    } finally {
      setIsSaving(false)
    }
  }

  const handleReset = async () => {
    setInputPath('')
    await handleSave('')
  }

  const handleCheckIntegrity = async () => {
    setIntegrityLoading(true)
    try {
      const res = await api.checkIntegrity()
      setIntegrityResult(res)
      if (res.ok) {
        toast.success('Integridad de SQLite FTS5 verificada correctamente.')
      } else {
        toast.error('Se detectaron anomalías en la base de conocimiento.')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al verificar integridad.')
    } finally {
      setIntegrityLoading(false)
    }
  }

  const handleRebuildIndex = async () => {
    setRebuildingIndex(true)
    try {
      const res = await api.rebuildIndex()
      toast.success(`Índice FTS5 reconstruido: ${res.chunks_reindexed} fragmentos reindexados.`)
      void handleCheckIntegrity()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al reconstruir índice.')
    } finally {
      setRebuildingIndex(false)
    }
  }

  const handleExportBackup = async () => {
    setExportingBackup(true)
    try {
      const res = await api.exportJsonBackup()
      toast.success(`Respaldo JSON generado con éxito (${res.manifest_path.split(/[/\\]/).pop()}).`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al exportar respaldo JSON.')
    } finally {
      setExportingBackup(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* 1. Storage Location Configuration Card */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-[#002777]">
              <Database className="h-6 w-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900">
                Base de Conocimiento Compartida (SQLite FTS5)
              </h3>
              <p className="text-xs text-slate-500">
                Almacén documental e indexación de texto completo BM25 con normalización de diacríticos en español.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ${
                isAccessible
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-red-50 text-red-700 border-red-200'
              }`}
            >
              {isAccessible ? (
                <>
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                  {isCustom ? 'Carpeta de Red Conectada' : 'Almacenamiento Local'}
                </>
              ) : (
                <>
                  <AlertTriangle className="h-3.5 w-3.5 text-red-600" />
                  Ruta no accesible
                </>
              )}
            </span>
          </div>
        </div>

        {/* Path Input Form */}
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-bold text-slate-700 block">
              Ruta de la Base de Conocimiento (Local o Red UNC)
            </label>
            {configuredPath && (
              <span className="text-[11px] font-mono text-slate-500">
                Configurado: {configuredPath}
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Folder className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <input
                type="text"
                value={inputPath}
                onChange={(e) => setInputPath(e.target.value)}
                placeholder="Ej: \\servidor\qa-mgmt\knowledge  o  D:\qa-mgmt\knowledge"
                disabled={isLoading || isSaving}
                className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-300 rounded-xl font-mono text-xs text-slate-900 focus:bg-white focus:ring-2 focus:ring-[#002777] focus:border-transparent outline-none transition"
              />
            </div>
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={isSaving || isLoading}
              className="px-5 py-2.5 bg-[#002777] hover:bg-[#001f5f] text-white text-xs font-bold rounded-xl transition shadow-xs disabled:opacity-50 flex items-center gap-2 cursor-pointer"
            >
              {isSaving && <RefreshCw className="h-3.5 w-3.5 animate-spin" />}
              <span>{isSaving ? 'Guardando...' : 'Guardar Ruta'}</span>
            </button>
            {isCustom && (
              <button
                type="button"
                onClick={() => void handleReset()}
                disabled={isSaving || isLoading}
                className="px-4 py-2.5 border border-slate-300 hover:bg-slate-100 text-slate-700 text-xs font-semibold rounded-xl transition disabled:opacity-50 cursor-pointer"
                title="Restaurar a la carpeta local predeterminada"
              >
                Restaurar Local
              </button>
            )}
          </div>
          <p className="text-[11px] text-slate-400">
            Deje en blanco para usar la ubicación local predeterminada. En carpetas de red, SQLite WAL garantiza concurrencia multi-usuario segura.
          </p>
        </div>

        {/* Active Resolved Path Display */}
        <div className="rounded-xl bg-slate-50 p-4 border border-slate-200/80 flex items-start gap-3">
          <HardDrive className="h-4 w-4 text-slate-500 shrink-0 mt-0.5" />
          <div className="space-y-1 min-w-0">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 block">
              Ruta física activa del motor SQLite
            </span>
            <p className="text-xs font-mono text-slate-700 break-all select-all font-semibold">
              {resolvedPath || 'Cargando ruta...'}
            </p>
          </div>
        </div>
      </div>

      {/* 2. Maintenance, Recovery & Integrity Tools */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-50 text-purple-700">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-slate-900">
              Mantenimiento, Integridad y Recuperación
            </h4>
            <p className="text-xs text-slate-500">
              Herramientas de diagnóstico para la base de datos FTS5, reindexación y exportación de respaldos.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
          {/* Check Integrity */}
          <button
            type="button"
            onClick={() => void handleCheckIntegrity()}
            disabled={integrityLoading}
            className="flex flex-col items-start p-4 rounded-xl border border-slate-200 hover:border-blue-300 hover:bg-blue-50/30 transition text-left group cursor-pointer"
          >
            <div className="flex items-center justify-between w-full mb-2">
              <ShieldCheck className="h-5 w-5 text-blue-600" />
              {integrityLoading && <RefreshCw className="h-3.5 w-3.5 animate-spin text-blue-600" />}
            </div>
            <span className="text-xs font-bold text-slate-800 group-hover:text-[#002777]">
              Verificar Integridad
            </span>
            <span className="text-[11px] text-slate-400 mt-1">
              Valida la consistencia de tablas y árboles FTS5.
            </span>
          </button>

          {/* Rebuild FTS Index */}
          <button
            type="button"
            onClick={() => void handleRebuildIndex()}
            disabled={rebuildingIndex}
            className="flex flex-col items-start p-4 rounded-xl border border-slate-200 hover:border-amber-300 hover:bg-amber-50/30 transition text-left group cursor-pointer"
          >
            <div className="flex items-center justify-between w-full mb-2">
              <FolderSync className="h-5 w-5 text-amber-600" />
              {rebuildingIndex && <RefreshCw className="h-3.5 w-3.5 animate-spin text-amber-600" />}
            </div>
            <span className="text-xs font-bold text-slate-800 group-hover:text-amber-800">
              Reconstruir Índice FTS5
            </span>
            <span className="text-[11px] text-slate-400 mt-1">
              Regenera el índice BM25 de todos los fragmentos.
            </span>
          </button>

          {/* Export JSON Backup */}
          <button
            type="button"
            onClick={() => void handleExportBackup()}
            disabled={exportingBackup}
            className="flex flex-col items-start p-4 rounded-xl border border-slate-200 hover:border-emerald-300 hover:bg-emerald-50/30 transition text-left group cursor-pointer"
          >
            <div className="flex items-center justify-between w-full mb-2">
              <FileDown className="h-5 w-5 text-emerald-600" />
              {exportingBackup && <RefreshCw className="h-3.5 w-3.5 animate-spin text-emerald-600" />}
            </div>
            <span className="text-xs font-bold text-slate-800 group-hover:text-emerald-800">
              Exportar Respaldo JSON
            </span>
            <span className="text-[11px] text-slate-400 mt-1">
              Genera archivos exportables de documentos y fragmentos.
            </span>
          </button>
        </div>

        {/* Integrity Check Results Box */}
        {integrityResult && (
          <div
            className={`mt-3 p-4 rounded-xl border text-xs font-mono space-y-1.5 ${
              integrityResult.ok
                ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
                : 'bg-red-50/70 border-red-200 text-red-900'
            }`}
          >
            <div className="flex items-center gap-2 font-bold font-sans">
              {integrityResult.ok ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              ) : (
                <AlertTriangle className="h-4 w-4 text-red-600" />
              )}
              <span>
                {integrityResult.ok
                  ? 'Estado: Base de datos íntegra y sin errores'
                  : 'Estado: Se encontraron advertencias o errores'}
              </span>
            </div>
            <ul className="list-disc list-inside text-[11px] opacity-90 pl-1 space-y-0.5">
              {integrityResult.details.map((detail: string, idx: number) => (
                <li key={idx}>{detail}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

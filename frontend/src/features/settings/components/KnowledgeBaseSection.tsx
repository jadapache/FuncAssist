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
  Server,
  Cpu,
  Layers,
  Sparkles,
} from 'lucide-react'
import { api, type KnowledgeIntegrityResponse, type KnowledgePathResponse } from '../../../api/client'
import { useToast } from '../../../context/ToastContext'

export const KnowledgeBaseSection = () => {
  const [dbInfo, setDbInfo] = useState<KnowledgePathResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Recovery tools state
  const [integrityLoading, setIntegrityLoading] = useState(false)
  const [integrityResult, setIntegrityResult] = useState<KnowledgeIntegrityResponse | null>(null)
  const [rebuildingIndex, setRebuildingIndex] = useState(false)
  const [exportingBackup, setExportingBackup] = useState(false)

  const { toast } = useToast()

  const loadStatus = async () => {
    setIsLoading(true)
    try {
      const res = await api.getKnowledgePath()
      setDbInfo(res)
    } catch {
      toast.error('No se pudo obtener el estado de la base de conocimiento.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    void loadStatus()
  }, [])

  const handleCheckIntegrity = async () => {
    setIntegrityLoading(true)
    try {
      const res = await api.checkIntegrity()
      setIntegrityResult(res)
      if (res.ok) {
        toast.success('Integridad del motor RAG verificada correctamente.')
      } else {
        toast.error('Se detectaron advertencias en la base de datos.')
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
      toast.success(`Índice RAG reconstruido: ${res.chunks_reindexed} fragmentos procesados.`)
      void handleCheckIntegrity()
      void loadStatus()
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

  const isPostgres = dbInfo?.engine === 'postgresql' || dbInfo?.is_custom
  const isConnected = dbInfo?.is_accessible !== false

  return (
    <div className="space-y-6">
      {/* 1. PostgreSQL RAG Server Status Card */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-[#002777]">
              <Database className="h-6 w-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900">
                Base de Conocimiento RAG (PostgreSQL & Vector)
              </h3>
              <p className="text-xs text-slate-500">
                Motor relacional y semántico alojado en servidor con indexación Full-Text en español y soporte vectorial.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ${
                isConnected
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-red-50 text-red-700 border-red-200'
              }`}
            >
              {isConnected ? (
                <>
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                  {isPostgres ? 'PostgreSQL Conectado' : 'Almacenamiento Local Activo'}
                </>
              ) : (
                <>
                  <AlertTriangle className="h-3.5 w-3.5 text-red-600" />
                  Error de Conexión
                </>
              )}
            </span>
          </div>
        </div>

        {/* Server Specs & Environment Notice */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
          {/* Engine & Host */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-1">
            <div className="flex items-center gap-2 text-slate-500 text-xs font-bold uppercase tracking-wider">
              <Server className="h-4 w-4 text-[#002777]" />
              <span>Motor Activo</span>
            </div>
            <p className="text-sm font-bold text-slate-900 capitalize">
              PostgreSQL
            </p>
            <p className="text-[11px] font-mono text-slate-500 truncate" title={dbInfo?.configured_path || 'Servidor'}>
              Host: {dbInfo?.configured_path || 'Servidor Administrado'}
            </p>
          </div>

          {/* Full-Text Search (Spanish) */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-1">
            <div className="flex items-center gap-2 text-slate-500 text-xs font-bold uppercase tracking-wider">
              <Layers className="h-4 w-4 text-emerald-600" />
              <span>Indexado Léxico</span>
            </div>
            <p className="text-sm font-bold text-slate-900">
              tsvector (Español) + GIN
            </p>
            <p className="text-[11px] text-slate-500">
              BM25 / ts_rank_cd con normalización de acentos.
            </p>
          </div>

          {/* Vector Capability */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-1">
            <div className="flex items-center gap-2 text-slate-500 text-xs font-bold uppercase tracking-wider">
              <Cpu className="h-4 w-4 text-purple-600" />
              <span>Alcance Vectorial</span>
            </div>
            <p className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
              <span>{dbInfo?.pgvector_enabled ? 'pgvector Activo' : 'Vectorial Habilitado'}</span>
              <Sparkles className="h-3.5 w-3.5 text-purple-500" />
            </p>
            <p className="text-[11px] text-slate-500">
              Similitud Coseno e índices HNSW para RAG.
            </p>
          </div>
        </div>

        {/* Environment Variable Management Banner */}
        <div className="rounded-xl bg-blue-50/60 p-4 border border-blue-200/70 flex items-start gap-3">
          <HardDrive className="h-4 w-4 text-[#002777] shrink-0 mt-0.5" />
          <div className="space-y-1 text-xs">
            <span className="font-bold text-[#002777] block">
              Administración mediante Variables de Entorno del Servidor
            </span>
            <p className="text-slate-600 leading-relaxed">
              La conexión a la base de datos se configura centralizadamente a través de{' '}
              <code className="px-1.5 py-0.5 rounded bg-blue-100 font-mono text-[#002777] font-semibold">
                KNOWLEDGE_DATABASE_URL
              </code>{' '}
              (o <code className="px-1.5 py-0.5 rounded bg-blue-100 font-mono text-[#002777] font-semibold">DATABASE_URL</code>).
              Los archivos adjuntos físicos se custodian de forma segura en el volumen de datos del servidor:
            </p>
            <p className="font-mono text-slate-700 text-[11px] pt-1 break-all select-all font-semibold">
              {dbInfo?.resolved_path || 'Cargando directorio...'}
            </p>
          </div>
        </div>
      </div>

      {/* 2. Maintenance, Recovery & Integrity Tools */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-50 text-purple-700">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-slate-900">
                Mantenimiento, Diagnóstico y Recuperación
              </h4>
              <p className="text-xs text-slate-500">
                Herramientas para verificar la consistencia del índice RAG, reindexación y exportación de respaldos.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void loadStatus()}
            disabled={isLoading}
            className="p-2 border border-slate-200 hover:bg-slate-50 rounded-xl text-slate-600 transition"
            title="Refrescar estado"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
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
              Verificar Conexión e Integridad
            </span>
            <span className="text-[11px] text-slate-400 mt-1">
              Valida la conectividad con PostgreSQL y la integridad de tablas y fragmentos.
            </span>
          </button>

          {/* Rebuild FTS & Vector Index */}
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
              Reconstruir Índices RAG
            </span>
            <span className="text-[11px] text-slate-400 mt-1">
              Reejecuta el reindexado de las tablas y fragmentos vectoriales y léxicos.
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
              Genera archivos exportables de documentos y fragmentos para respaldo.
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
                  ? 'Estado: Base de datos RAG íntegra y conectada'
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

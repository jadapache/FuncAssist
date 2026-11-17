import {
  Activity,
  ClipboardCheck,
  Eye,
  FileSearch,
  GitCompareArrows,
  LayoutGrid,
  MessageSquare,
  Mic,
  Sun,
  TestTube2,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import { DEFAULT_DISPLAY_NAME } from '../constants/app'
import { PageHeader } from '../components/common/PageHeader'
import { DashboardSkeleton } from '../components/common/Skeleton'
import { QuickActionCard } from '../components/ui/QuickActionCard'
import { useUser } from '../context/UserContext'

type OutletContext = {
  displayName?: string
}

const getGreeting = () => {
  const hour = new Date().getHours()
  if (hour < 12) return '¡Buenos días!'
  if (hour < 17) return '¡Buenas tardes!'
  return '¡Buenas noches!'
}

export const DashboardPage = () => {
  const outletCtx = useOutletContext<OutletContext | undefined>()
  const displayName = outletCtx?.displayName || DEFAULT_DISPLAY_NAME
  const { user } = useUser()
  const [backendOk, setBackendOk] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
    const load = async () => {
      setLoading(true)
      try {
        await api.health()
        setBackendOk(true)
      } catch {
        setBackendOk(false)
      }
      setLoading(false)
    }
    void load()
  }, [])

  const role = user?.user_role || 'admin'
  const loggedInName = user?.display_name || displayName

  return (
    <div className={`flex flex-col min-h-full transition-all duration-700 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3'}`}>
      <PageHeader
        title="Inicio"
      />

      <div className="flex-1 px-4 py-6 md:px-8 max-w-7xl mx-auto w-full space-y-8 pb-12">
        {loading ? (
          <DashboardSkeleton />
        ) : (
          <>
            {/* Hero */}
            <section className="relative overflow-hidden rounded-3xl border border-blue-900/30 bg-gradient-to-br from-[#002777] via-[#003685] to-[#004497] p-6 text-white shadow-xl shadow-[#002777]/30 md:p-8">
              <div className="pointer-events-none absolute -left-10 -top-10 h-40 w-40 rounded-full bg-white/10 blur-3xl animate-float" aria-hidden />
              <div className="pointer-events-none absolute -bottom-16 -right-10 h-48 w-48 rounded-full bg-cyan-400/20 blur-3xl animate-float-delayed" aria-hidden />

              <div className="relative flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
                <div>
                  <h1 className="mt-4 text-3xl font-bold tracking-tight md:text-4xl">
                    {getGreeting()}, {loggedInName}
                  </h1>
                  <p className="mt-2 max-w-2xl text-sm text-blue-100 md:text-base">
                    Obtiene contexto en tiempo real de Jira, GitHub y tus documentos para responder con referencias precisas sin alucinaciones.
                  </p>
                </div>

                {/* Estado del sistema (Backend Health) */}
                <div className="flex shrink-0 flex-col items-center gap-3 rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-md min-w-[210px] shadow-sm">
                  <div className="w-full text-center text-sm font-medium text-blue-100">
                    Estado del sistema
                  </div>
                  <div className="flex items-center gap-3">
                    <div
                      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/20 shadow-sm backdrop-blur-sm ${backendOk
                        ? 'bg-emerald-500/20 text-emerald-300'
                        : backendOk === false
                          ? 'bg-amber-500/20 text-amber-300'
                          : 'bg-white/10 text-cyan-300'
                        }`}
                    >
                      <Activity className="h-5 w-5" aria-hidden />
                    </div>
                    <div className="flex flex-col">
                      <div className="flex items-center gap-2">
                        <span
                          className={`h-2.5 w-2.5 rounded-full ${backendOk
                            ? 'bg-emerald-400 animate-pulse'
                            : backendOk === false
                              ? 'bg-amber-400'
                              : 'bg-slate-300 animate-pulse'
                            }`}
                        />
                        <span className="text-xl font-bold tracking-tight text-white">
                          {backendOk === null ? '…' : backendOk ? 'En línea' : 'Desconectado'}
                        </span>
                      </div>
                      <span className="text-[11px] text-blue-200">
                        {backendOk === null ? 'Verificando estado' : backendOk ? 'API respondiendo' : 'Inicia el servidor FastAPI'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* Quick actions */}
            <section aria-label="Acciones rápidas">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-[var(--color-ink)]">Acciones rápidas</h2>
                <span className="text-xs text-[var(--color-ink-muted)]">Flujos de trabajo en un clic</span>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {role === 'funcional' ? (
                  <>
                    <QuickActionCard
                      to="/transcripciones"
                      title="Transcripción de Reuniones"
                      description="Convierte audio de reuniones en notas y especificaciones funcionales."
                      icon={Mic}
                      badge="Nuevo"
                      gradient="from-[#002777] to-[#004497]"
                    />
                    <QuickActionCard
                      to="/chat?new=1"
                      title="Chat"
                      description="Asistente interactivo para generar y mantener documentos de mejoras y requerimientos."
                      icon={MessageSquare}
                      gradient="from-[#004497] to-blue-600"
                    />
                    <QuickActionCard
                      to="/chat?new=1&skill=inventario_doc"
                      title="Inventario"
                      description="Catálogo de componentes, módulos y funcionalidades."
                      icon={LayoutGrid}
                      gradient="from-blue-800 to-[#002777]"
                    />
                    <QuickActionCard
                      to="/chat?new=1&skill=levantamiento_doc"
                      title="Levantamiento"
                      description="Estructuración y desglose de requerimientos del cliente."
                      icon={FileSearch}
                      gradient="from-blue-900 to-[#002777]"
                    />
                  </>
                ) : role === 'qa' ? (
                  <>
                    <QuickActionCard
                      to="/chat?new=1&skill=regression"
                      title="Regresión QA"
                      description="Ejecuta y valida casos de prueba de regresión automatizados."
                      icon={TestTube2}
                      badge="En vivo"
                      gradient="from-[#002777] to-[#004497]"
                    />
                    <QuickActionCard
                      to="/chat?new=1&skill=api_qa"
                      title="QA de API"
                      description="Pruebas de contratos, validación de endpoints y respuestas JSON."
                      icon={ClipboardCheck}
                      badge="Nuevo"
                      gradient="from-[#004497] to-blue-600"
                    />
                    <QuickActionCard
                      to="/chat?new=1&skill=visual_qa"
                      title="QA Visual"
                      description="Inspección visual de interfaces y análisis de discrepancias."
                      icon={Eye}
                      gradient="from-blue-900 to-[#002777]"
                    />
                  </>
                ) : (
                  <>
                    <QuickActionCard
                      to="/chat?new=1&skill=standup"
                      title="Generar Standup"
                      description="Ayer, hoy, bloqueos — obtenido automáticamente de Jira y GitHub."
                      icon={Sun}
                      badge="En vivo"
                      gradient="from-[#002777] to-[#004497]"
                    />
                    <QuickActionCard
                      to="/chat?new=1&skill=prd_checker"
                      title="Revisor de PRD"
                      description="Analiza especificaciones, revisa vacíos y evalúa criterios."
                      icon={FileSearch}
                      badge="Nuevo"
                      gradient="from-[#004497] to-blue-600"
                    />
                    <QuickActionCard
                      to="/chat?new=1&skill=change_impact"
                      title="Impacto de Cambios"
                      description="Mapea tickets, Pull Requests y documentos afectados por un cambio."
                      icon={GitCompareArrows}
                      badge="Nuevo"
                      gradient="from-blue-900 to-[#002777]"
                    />
                  </>
                )}
                <QuickActionCard
                  to="/knowledge/ask"
                  title="Consultar Producto"
                  description="Realiza consultas a tus documentos con fuentes citadas."
                  icon={MessageSquare}
                  badge="IA"
                  gradient="from-cyan-600 to-teal-600"
                />
              </div>
              <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <QuickActionCard
                  to="/knowledge"
                  title="Biblioteca & Documentos"
                  description="Explora o sube documentos, especificaciones y requerimientos para RAG."
                  icon={LayoutGrid}
                  gradient="from-teal-600 to-emerald-600"
                />
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  )
}

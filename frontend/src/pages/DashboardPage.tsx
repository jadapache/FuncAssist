import {
  Activity,
  ArrowRight,
  Bot,
  Brain,
  ClipboardCheck,
  ClipboardList,
  Eye,
  FileSearch,
  FileText,
  GitBranch,
  GitCompareArrows,
  Kanban,
  LayoutGrid,
  MessageSquare,
  Mic,
  Plug,
  Sparkles,
  Sun,
  TestTube2,
  Zap,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import { IntegrationTile } from '../components/ui/IntegrationTile'
import { QuickActionCard } from '../components/ui/QuickActionCard'
import { StatCard } from '../components/ui/StatCard'
import { useUser } from '../context/UserContext'
import type { IntegrationInfo } from '../types'

type OutletContext = {
  displayName: string
}

const getGreeting = () => {
  const hour = new Date().getHours()
  if (hour < 12) return '¡Buenos días!'
  if (hour < 17) return '¡Buenas tardes!'
  return '¡Buenas noches!'
}

export const DashboardPage = () => {
  const { displayName } = useOutletContext<OutletContext>()
  const [integrations, setIntegrations] = useState<IntegrationInfo[]>([])
  const [backendOk, setBackendOk] = useState<boolean | null>(null)
  const [aiConfigured, setAiConfigured] = useState<boolean | null>(null)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
    const load = async () => {
      try {
        await api.health()
        setBackendOk(true)
        const [items, ai] = await Promise.all([api.getIntegrations(), api.getAiSettings()])
        setIntegrations(items)
        setAiConfigured(Boolean(ai.provider))
      } catch {
        setBackendOk(false)
        setAiConfigured(false)
      }
    }
    void load()
  }, [])

  const jira = integrations.find((item) => item.id === 'jira')
  const github = integrations.find((item) => item.id === 'github')
  const gitlab = integrations.find((item) => item.id === 'gitlab')
  const connectedCount = integrations.filter((item) => item.status === 'connected').length
  const totalIntegrations = integrations.length

  const readiness = useMemo(() => {
    let score = 20
    if (backendOk) score += 25
    if (jira?.status === 'connected') score += 25
    if (github?.status === 'connected') score += 20
    if (aiConfigured) score += 10
    return Math.min(score, 100)
  }, [backendOk, jira, github, aiConfigured])

  const { user } = useUser()
  const role = user?.user_role || 'admin'

  return (
    <div className={`space-y-8 transition-all duration-700 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3'}`}>
      {/* Hero */}
      <section className="relative overflow-hidden rounded-3xl border border-blue-900/30 bg-gradient-to-br from-[#002777] via-[#003685] to-[#004497] p-6 text-white shadow-xl shadow-[#002777]/30 md:p-8">
        <div className="pointer-events-none absolute -left-10 -top-10 h-40 w-40 rounded-full bg-white/10 blur-3xl animate-float" aria-hidden />
        <div className="pointer-events-none absolute -bottom-16 -right-10 h-48 w-48 rounded-full bg-cyan-400/20 blur-3xl animate-float-delayed" aria-hidden />

        <div className="relative flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="mt-4 text-3xl font-bold tracking-tight md:text-4xl">
              {getGreeting()}, {displayName}
            </h1>
            <p className="mt-2 max-w-xl text-sm text-blue-100 md:text-base">
              Obtiene contexto en tiempo real de Jira, GitHub y tus documentos para responder con referencias precisas sin alucinaciones.
            </p>
          </div>

          <div className="flex shrink-0 flex-col items-start gap-3 rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-md md:items-end">
            <div className="flex items-center gap-2 text-sm text-blue-100">
              <Bot className="h-4 w-4" aria-hidden />
              Estado del sistema
            </div>
            <div className="flex items-end gap-2">
              <span className="text-4xl font-bold">{readiness}%</span>
              <span className="mb-1 text-xs text-blue-200">listo</span>
            </div>
            <div className="h-2 w-full min-w-[180px] overflow-hidden rounded-full bg-white/20">
              <div
                className="h-full rounded-full bg-gradient-to-r from-amber-300 to-cyan-300 transition-all duration-1000 ease-out"
                style={{ width: `${readiness}%` }}
              />
            </div>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section aria-label="Métricas del sistema" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Backend"
          value={backendOk === null ? '…' : backendOk ? 'En línea' : 'Desconectado'}
          icon={Activity}
          accent={backendOk ? 'emerald' : 'amber'}
          trend={backendOk ? 'API respondiendo' : 'Inicia el servidor FastAPI'}
          loading={backendOk === null}
        />
        <StatCard
          label="Integraciones"
          value={totalIntegrations ? `${connectedCount} / ${totalIntegrations}` : `${connectedCount}`}
          icon={Plug}
          accent="cyan"
          trend={connectedCount === totalIntegrations && totalIntegrations > 0 ? 'Todas las fuentes vinculadas' : 'Conecta Jira, GitHub y GitLab'}
          to="/settings?tab=integrations"
        />
        <StatCard
          label="Proveedor de IA"
          value={aiConfigured === null ? '…' : aiConfigured ? 'Configurado' : 'Requiere config.'}
          icon={Brain}
          accent={aiConfigured ? 'primary' : 'amber'}
          trend={aiConfigured ? 'Listo para ejecuciones' : 'Añade la clave en Configuración'}
          loading={aiConfigured === null}
          to="/settings"
        />
        <StatCard
          label="Búsqueda RAG"
          value="BM25"
          icon={Zap}
          accent="primary"
          trend="Contexto en vivo y documentos"
          to="/knowledge"
        />
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
                to="/funcional/transcripciones"
                title="Transcripción de Reuniones"
                description="Convierte audio de reuniones en notas y especificaciones funcionales."
                icon={Mic}
                badge="Nuevo"
                gradient="from-[#002777] to-[#004497]"
              />
              <QuickActionCard
                to="/funcional/inventario"
                title="Inventario"
                description="Catálogo de componentes, módulos y funcionalidades."
                icon={FileText}
                gradient="from-[#004497] to-blue-600"
              />
              <QuickActionCard
                to="/funcional/levantamiento"
                title="Levantamiento"
                description="Estructuración y desglose de requerimientos del cliente."
                icon={ClipboardList}
                gradient="from-blue-900 to-[#002777]"
              />
            </>
          ) : role === 'qa' ? (
            <>
              <QuickActionCard
                to="/qa/regression"
                title="Regresión QA"
                description="Ejecuta y valida casos de prueba de regresión automatizados."
                icon={TestTube2}
                badge="En vivo"
                gradient="from-[#002777] to-[#004497]"
              />
              <QuickActionCard
                to="/qa/api-qa"
                title="QA de API"
                description="Pruebas de contratos, validación de endpoints y respuestas JSON."
                icon={ClipboardCheck}
                badge="Nuevo"
                gradient="from-[#004497] to-blue-600"
              />
              <QuickActionCard
                to="/qa/visual-qa"
                title="QA Visual"
                description="Inspección visual de interfaces y análisis de discrepancias."
                icon={Eye}
                gradient="from-blue-900 to-[#002777]"
              />
            </>
          ) : (
            <>
              <QuickActionCard
                to="/pm/standup"
                title="Generar Standup"
                description="Ayer, hoy, bloqueos — obtenido automáticamente de Jira y GitHub."
                icon={Sun}
                badge="En vivo"
                gradient="from-[#002777] to-[#004497]"
              />
              <QuickActionCard
                to="/pm/prd-checker"
                title="Revisor de PRD"
                description="Analiza especificaciones, revisa vacíos y evalúa criterios."
                icon={FileSearch}
                badge="Nuevo"
                gradient="from-[#004497] to-blue-600"
              />
              <QuickActionCard
                to="/pm/change-impact"
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
          <QuickActionCard
            to="/settings?tab=integrations"
            title="Conectar Fuentes"
            description="Configura Jira OAuth, GitHub PAT y GitLab PAT."
            icon={GitBranch}
            gradient="from-blue-700 to-cyan-700"
          />
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-5">
        {/* Integrations */}
        <section aria-label="Integraciones" className="space-y-4 xl:col-span-2">
          <h2 className="text-lg font-semibold text-[var(--color-ink)]">Conexiones activas</h2>
          <IntegrationTile
            name="Jira"
            connected={jira?.status === 'connected'}
            detail={
              jira?.status === 'connected'
                ? `${jira.workspace_label ?? 'Espacio'} · ${jira.account_label ?? ''}`
                : 'OAuth o PAT — tickets y sprints'
            }
            icon={Kanban}
            iconBg="bg-blue-100 text-blue-600"
          />
          <IntegrationTile
            name="GitHub"
            connected={github?.status === 'connected'}
            detail={
              github?.status === 'connected'
                ? `Conectado como ${github.account_label}`
                : 'PAT + repositorios seleccionados'
            }
            icon={GitBranch}
            iconBg="bg-gray-900 text-white"
          />
          <IntegrationTile
            name="GitLab"
            connected={gitlab?.status === 'connected'}
            detail={
              gitlab?.status === 'connected'
                ? `Conectado como ${gitlab.account_label}`
                : 'PAT + proyectos seleccionados'
            }
            icon={GitBranch}
            iconBg="bg-orange-500 text-white"
          />
        </section>

        {/* AI contract + activity */}
        <section className="xl:col-span-3">
          <div className="h-full rounded-2xl border border-[var(--color-border)] bg-white p-6 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-[#002777]">
                <Sparkles className="h-5 w-5" aria-hidden />
              </div>
              <div>
                <h2 className="font-semibold text-[var(--color-ink)]">Reglas de IA y Fundamentación</h2>
                <p className="text-xs text-[var(--color-ink-muted)]">Cada respuesta sigue estrictos criterios de precisión</p>
              </div>
            </div>

            <ul className="mt-5 space-y-3">
              {[
                { step: '1', text: 'Declarar las fuentes permitidas por cada función' },
                { step: '2', text: 'Consolidar el contexto de las APIs en vivo y documentos cargados' },
                { step: '3', text: 'Responder únicamente con base en evidencia — sin suposiciones generadas' },
                { step: '4', text: 'Incluir referencias y citas explícitas para cada respuesta' },
              ].map((item) => (
                <li
                  key={item.step}
                  className="flex items-start gap-3 rounded-xl border border-transparent p-3 transition-colors hover:border-blue-100 hover:bg-blue-50/50"
                >
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-100 text-xs font-bold text-[#002777]">
                    {item.step}
                  </span>
                  <span className="text-sm text-[var(--color-ink-muted)]">{item.text}</span>
                </li>
              ))}
            </ul>

            <div className="mt-6 flex flex-wrap gap-3 border-t border-[var(--color-border)] pt-5">
              {role === 'funcional' ? (
                <Link to="/funcional/transcripciones" className="btn-primary gap-2">
                  <Mic className="h-4 w-4" aria-hidden />
                  Transcripciones
                </Link>
              ) : role === 'qa' ? (
                <Link to="/qa/regression" className="btn-primary gap-2">
                  <TestTube2 className="h-4 w-4" aria-hidden />
                  Probar Regresión
                </Link>
              ) : (
                <Link to="/pm/standup" className="btn-primary gap-2">
                  <Sun className="h-4 w-4" aria-hidden />
                  Probar Standup
                </Link>
              )}
              <Link to="/settings" className="btn-secondary gap-2">
                Configurar IA
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Link>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

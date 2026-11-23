import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core'
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
} from 'lucide'
import { api } from '../../api/client'
import { UserService } from '../../core/auth/user.service'
import { LayoutContextService } from '../../core/layout/layout-context.service'
import { PageHeaderComponent } from '../../shared/components/page-header.component'
import { QuickActionCardComponent } from '../../shared/components/quick-action-card.component'
import { DashboardSkeletonComponent } from '../../shared/components/skeleton.component'
import { LucideIconDirective } from '../../shared/icons/lucide.directive'

const getGreeting = () => {
  const hour = new Date().getHours()
  if (hour < 12) return '¡Buenos días!'
  if (hour < 17) return '¡Buenas tardes!'
  return '¡Buenas noches!'
}

/** Home page (port of React `DashboardPage`). */
@Component({
  selector: 'app-dashboard-page',
  imports: [PageHeaderComponent, QuickActionCardComponent, DashboardSkeletonComponent, LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div
      [class]="
        'flex flex-col min-h-full transition-all duration-700 ' +
        (mounted() ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3')
      "
    >
      <app-page-header title="Inicio" />

      <div class="flex-1 px-4 py-6 md:px-8 max-w-7xl mx-auto w-full space-y-8 pb-12">
        @if (loading()) {
          <app-dashboard-skeleton />
        } @else {
          <!-- Hero -->
          <section
            class="relative overflow-hidden rounded-3xl border border-blue-900/30 bg-gradient-to-br from-[#002777] via-[#003685] to-[#004497] p-6 text-white shadow-xl shadow-[#002777]/30 md:p-8"
          >
            <div
              class="pointer-events-none absolute -left-10 -top-10 h-40 w-40 rounded-full bg-white/10 blur-3xl animate-float"
              aria-hidden="true"
            ></div>
            <div
              class="pointer-events-none absolute -bottom-16 -right-10 h-48 w-48 rounded-full bg-cyan-400/20 blur-3xl animate-float-delayed"
              aria-hidden="true"
            ></div>

            <div class="relative flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
              <div>
                <h1 class="mt-4 text-3xl font-bold tracking-tight md:text-4xl">{{ greeting }}, {{ loggedInName() }}</h1>
                <p class="mt-2 max-w-2xl text-sm text-blue-100 md:text-base">
                  Obtiene contexto en tiempo real de Jira, GitHub y tus documentos para responder con referencias precisas
                  sin alucinaciones.
                </p>
              </div>

              <!-- Estado del sistema (Backend Health) -->
              <div
                class="flex shrink-0 flex-col items-center gap-3 rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-md min-w-[210px] shadow-sm"
              >
                <div class="w-full text-center text-sm font-medium text-blue-100">Estado del sistema</div>
                <div class="flex items-center gap-3">
                  <div
                    [class]="
                      'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/20 shadow-sm backdrop-blur-sm ' +
                      (backendOk()
                        ? 'bg-emerald-500/20 text-emerald-300'
                        : backendOk() === false
                          ? 'bg-amber-500/20 text-amber-300'
                          : 'bg-white/10 text-cyan-300')
                    "
                  >
                    <svg [lucide]="icons.Activity" class="h-5 w-5"></svg>
                  </div>
                  <div class="flex flex-col">
                    <div class="flex items-center gap-2">
                      <span
                        [class]="
                          'h-2.5 w-2.5 rounded-full ' +
                          (backendOk()
                            ? 'bg-emerald-400 animate-pulse'
                            : backendOk() === false
                              ? 'bg-amber-400'
                              : 'bg-slate-300 animate-pulse')
                        "
                      ></span>
                      <span class="text-xl font-bold tracking-tight text-white">
                        {{ backendOk() === null ? '…' : backendOk() ? 'En línea' : 'Desconectado' }}
                      </span>
                    </div>
                    <span class="text-[11px] text-blue-200">
                      {{
                        backendOk() === null
                          ? 'Verificando estado'
                          : backendOk()
                            ? 'API respondiendo'
                            : 'Inicia el servidor FastAPI'
                      }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <!-- Quick actions -->
          <section aria-label="Acciones rápidas">
            <div class="mb-4 flex items-center justify-between">
              <h2 class="text-lg font-semibold text-[var(--color-ink)]">Acciones rápidas</h2>
              <span class="text-xs text-[var(--color-ink-muted)]">Flujos de trabajo en un clic</span>
            </div>
            <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              @if (role() === 'funcional') {
                <app-quick-action-card
                  to="/transcripciones"
                  title="Transcripción de Reuniones"
                  description="Convierte audio de reuniones en notas y especificaciones funcionales."
                  [icon]="icons.Mic"
                  badge="Nuevo"
                  gradient="from-[#002777] to-[#004497]"
                />
                <app-quick-action-card
                  to="/chat?new=1"
                  title="Chat"
                  description="Asistente interactivo para generar y mantener documentos de mejoras y requerimientos."
                  [icon]="icons.MessageSquare"
                  gradient="from-[#004497] to-blue-600"
                />
                <app-quick-action-card
                  to="/chat?new=1&skill=inventario_doc"
                  title="Inventario"
                  description="Catálogo de componentes, módulos y funcionalidades."
                  [icon]="icons.LayoutGrid"
                  gradient="from-blue-800 to-[#002777]"
                />
                <app-quick-action-card
                  to="/chat?new=1&skill=levantamiento_doc"
                  title="Levantamiento"
                  description="Estructuración y desglose de requerimientos del cliente."
                  [icon]="icons.FileSearch"
                  gradient="from-blue-900 to-[#002777]"
                />
              } @else if (role() === 'qa') {
                <app-quick-action-card
                  to="/chat?new=1&skill=regression"
                  title="Regresión QA"
                  description="Ejecuta y valida casos de prueba de regresión automatizados."
                  [icon]="icons.TestTube2"
                  badge="En vivo"
                  gradient="from-[#002777] to-[#004497]"
                />
                <app-quick-action-card
                  to="/chat?new=1&skill=api_qa"
                  title="QA de API"
                  description="Pruebas de contratos, validación de endpoints y respuestas JSON."
                  [icon]="icons.ClipboardCheck"
                  badge="Nuevo"
                  gradient="from-[#004497] to-blue-600"
                />
                <app-quick-action-card
                  to="/chat?new=1&skill=visual_qa"
                  title="QA Visual"
                  description="Inspección visual de interfaces y análisis de discrepancias."
                  [icon]="icons.Eye"
                  gradient="from-blue-900 to-[#002777]"
                />
              } @else {
                <app-quick-action-card
                  to="/chat?new=1&skill=standup"
                  title="Generar Standup"
                  description="Ayer, hoy, bloqueos — obtenido automáticamente de Jira y GitHub."
                  [icon]="icons.Sun"
                  badge="En vivo"
                  gradient="from-[#002777] to-[#004497]"
                />
                <app-quick-action-card
                  to="/chat?new=1&skill=prd_checker"
                  title="Revisor de PRD"
                  description="Analiza especificaciones, revisa vacíos y evalúa criterios."
                  [icon]="icons.FileSearch"
                  badge="Nuevo"
                  gradient="from-[#004497] to-blue-600"
                />
                <app-quick-action-card
                  to="/chat?new=1&skill=change_impact"
                  title="Impacto de Cambios"
                  description="Mapea tickets, Pull Requests y documentos afectados por un cambio."
                  [icon]="icons.GitCompareArrows"
                  badge="Nuevo"
                  gradient="from-blue-900 to-[#002777]"
                />
              }
              <app-quick-action-card
                to="/knowledge/ask"
                title="Consultar Producto"
                description="Realiza consultas a tus documentos con fuentes citadas."
                [icon]="icons.MessageSquare"
                badge="IA"
                gradient="from-cyan-600 to-teal-600"
              />
            </div>
            <div class="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <app-quick-action-card
                to="/knowledge"
                title="Biblioteca & Documentos"
                description="Explora o sube documentos, especificaciones y requerimientos para RAG."
                [icon]="icons.LayoutGrid"
                gradient="from-teal-600 to-emerald-600"
              />
            </div>
          </section>
        }
      </div>
    </div>
  `,
})
export class DashboardPageComponent implements OnInit {
  private readonly userService = inject(UserService)
  private readonly layout = inject(LayoutContextService)

  protected readonly icons = {
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
  }
  protected readonly greeting = getGreeting()
  protected readonly backendOk = signal<boolean | null>(null)
  protected readonly loading = signal(true)
  protected readonly mounted = signal(false)

  protected readonly role = computed(() => this.userService.user()?.user_role || 'admin')
  protected readonly loggedInName = computed(() => this.userService.user()?.display_name || this.layout.displayName())

  async ngOnInit(): Promise<void> {
    // Next frame so the fade/slide-in transition runs like the React mount effect.
    requestAnimationFrame(() => this.mounted.set(true))
    this.loading.set(true)
    try {
      await api.health()
      this.backendOk.set(true)
    } catch {
      this.backendOk.set(false)
    }
    this.loading.set(false)
  }
}

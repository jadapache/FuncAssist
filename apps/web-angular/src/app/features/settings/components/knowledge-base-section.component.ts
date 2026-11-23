import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core'
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Database,
  FileDown,
  FolderSync,
  HardDrive,
  Layers,
  RefreshCw,
  Server,
  ShieldCheck,
  Sparkles,
} from 'lucide'
import { api, type KnowledgeIntegrityResponse, type KnowledgePathResponse } from '../../../api/client'
import { ToastService } from '../../../core/notifications/toast.service'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'

/** Port of React `KnowledgeBaseSection`. */
@Component({
  selector: 'app-knowledge-base-section',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="space-y-6">
      <!-- 1. PostgreSQL RAG Server Status Card -->
      <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-5">
        <div class="flex items-start justify-between gap-4">
          <div class="flex items-center gap-3">
            <div class="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-[#002777]">
              <svg [lucide]="icons.Database" class="h-6 w-6"></svg>
            </div>
            <div>
              <h3 class="text-base font-bold text-slate-900">Base de Conocimiento RAG (PostgreSQL &amp; Vector)</h3>
              <p class="text-xs text-slate-500">
                Motor relacional y semántico alojado en servidor con indexación Full-Text en español y soporte vectorial.
              </p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span
              [class]="
                'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ' +
                (isConnected()
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-red-50 text-red-700 border-red-200')
              "
            >
              @if (isConnected()) {
                <svg [lucide]="icons.CheckCircle2" class="h-3.5 w-3.5 text-emerald-600"></svg>
                {{ isPostgres() ? 'PostgreSQL Conectado' : 'Almacenamiento Local Activo' }}
              } @else {
                <svg [lucide]="icons.AlertTriangle" class="h-3.5 w-3.5 text-red-600"></svg>
                Error de Conexión
              }
            </span>
          </div>
        </div>

        <!-- Server Specs & Environment Notice -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
          <!-- Engine & Host -->
          <div class="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-1">
            <div class="flex items-center gap-2 text-slate-500 text-xs font-bold uppercase tracking-wider">
              <svg [lucide]="icons.Server" class="h-4 w-4 text-[#002777]"></svg>
              <span>Motor Activo</span>
            </div>
            <p class="text-sm font-bold text-slate-900 capitalize">PostgreSQL</p>
            <p class="text-[11px] font-mono text-slate-500 truncate" [title]="dbInfo()?.configured_path || 'Servidor'">
              Host: {{ dbInfo()?.configured_path || 'Servidor Administrado' }}
            </p>
          </div>

          <!-- Full-Text Search (Spanish) -->
          <div class="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-1">
            <div class="flex items-center gap-2 text-slate-500 text-xs font-bold uppercase tracking-wider">
              <svg [lucide]="icons.Layers" class="h-4 w-4 text-emerald-600"></svg>
              <span>Indexado Léxico</span>
            </div>
            <p class="text-sm font-bold text-slate-900">tsvector (Español) + GIN</p>
            <p class="text-[11px] text-slate-500">BM25 / ts_rank_cd con normalización de acentos.</p>
          </div>

          <!-- Vector Capability -->
          <div class="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-1">
            <div class="flex items-center gap-2 text-slate-500 text-xs font-bold uppercase tracking-wider">
              <svg [lucide]="icons.Cpu" class="h-4 w-4 text-purple-600"></svg>
              <span>Alcance Vectorial</span>
            </div>
            <p class="text-sm font-bold text-slate-900 flex items-center gap-1.5">
              <span>{{ dbInfo()?.pgvector_enabled ? 'pgvector Activo' : 'Vectorial Habilitado' }}</span>
              <svg [lucide]="icons.Sparkles" class="h-3.5 w-3.5 text-purple-500"></svg>
            </p>
            <p class="text-[11px] text-slate-500">Similitud Coseno e índices HNSW para RAG.</p>
          </div>
        </div>

        <!-- Environment Variable Management Banner -->
        <div class="rounded-xl bg-blue-50/60 p-4 border border-blue-200/70 flex items-start gap-3">
          <svg [lucide]="icons.HardDrive" class="h-4 w-4 text-[#002777] shrink-0 mt-0.5"></svg>
          <div class="space-y-1 text-xs">
            <span class="font-bold text-[#002777] block"> Administración mediante Variables de Entorno del Servidor </span>
            <p class="text-slate-600 leading-relaxed">
              La conexión a la base de datos se configura centralizadamente a través de{{ ' ' }}<code
                class="px-1.5 py-0.5 rounded bg-blue-100 font-mono text-[#002777] font-semibold"
                >DATABASE_URL</code
              >. Los archivos adjuntos físicos se custodian de forma segura en el volumen de datos del servidor:
            </p>
            <p class="font-mono text-slate-700 text-[11px] pt-1 break-all select-all font-semibold">
              {{ dbInfo()?.resolved_path || 'Cargando directorio...' }}
            </p>
          </div>
        </div>
      </div>

      <!-- 2. Maintenance, Recovery & Integrity Tools -->
      <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-50 text-purple-700">
              <svg [lucide]="icons.ShieldCheck" class="h-5 w-5"></svg>
            </div>
            <div>
              <h4 class="text-sm font-bold text-slate-900">Mantenimiento, Diagnóstico y Recuperación</h4>
              <p class="text-xs text-slate-500">
                Herramientas para verificar la consistencia del índice RAG, reindexación y exportación de respaldos.
              </p>
            </div>
          </div>
          <button
            type="button"
            (click)="loadStatus()"
            [disabled]="isLoading()"
            class="p-2 border border-slate-200 hover:bg-slate-50 rounded-xl text-slate-600 transition"
            title="Refrescar estado"
          >
            <svg [lucide]="icons.RefreshCw" [class]="'h-4 w-4 ' + (isLoading() ? 'animate-spin' : '')"></svg>
          </button>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
          <!-- Check Integrity -->
          <button
            type="button"
            (click)="handleCheckIntegrity()"
            [disabled]="integrityLoading()"
            class="flex flex-col items-start p-4 rounded-xl border border-slate-200 hover:border-blue-300 hover:bg-blue-50/30 transition text-left group cursor-pointer"
          >
            <div class="flex items-center justify-between w-full mb-2">
              <svg [lucide]="icons.ShieldCheck" class="h-5 w-5 text-blue-600"></svg>
              @if (integrityLoading()) {
                <svg [lucide]="icons.RefreshCw" class="h-3.5 w-3.5 animate-spin text-blue-600"></svg>
              }
            </div>
            <span class="text-xs font-bold text-slate-800 group-hover:text-[#002777]">
              Verificar Conexión e Integridad
            </span>
            <span class="text-[11px] text-slate-400 mt-1">
              Valida la conectividad con PostgreSQL y la integridad de tablas y fragmentos.
            </span>
          </button>

          <!-- Rebuild FTS & Vector Index -->
          <button
            type="button"
            (click)="handleRebuildIndex()"
            [disabled]="rebuildingIndex()"
            class="flex flex-col items-start p-4 rounded-xl border border-slate-200 hover:border-amber-300 hover:bg-amber-50/30 transition text-left group cursor-pointer"
          >
            <div class="flex items-center justify-between w-full mb-2">
              <svg [lucide]="icons.FolderSync" class="h-5 w-5 text-amber-600"></svg>
              @if (rebuildingIndex()) {
                <svg [lucide]="icons.RefreshCw" class="h-3.5 w-3.5 animate-spin text-amber-600"></svg>
              }
            </div>
            <span class="text-xs font-bold text-slate-800 group-hover:text-amber-800"> Reconstruir Índices RAG </span>
            <span class="text-[11px] text-slate-400 mt-1">
              Reejecuta el reindexado de las tablas y fragmentos vectoriales y léxicos.
            </span>
          </button>

          <!-- Export JSON Backup -->
          <button
            type="button"
            (click)="handleExportBackup()"
            [disabled]="exportingBackup()"
            class="flex flex-col items-start p-4 rounded-xl border border-slate-200 hover:border-emerald-300 hover:bg-emerald-50/30 transition text-left group cursor-pointer"
          >
            <div class="flex items-center justify-between w-full mb-2">
              <svg [lucide]="icons.FileDown" class="h-5 w-5 text-emerald-600"></svg>
              @if (exportingBackup()) {
                <svg [lucide]="icons.RefreshCw" class="h-3.5 w-3.5 animate-spin text-emerald-600"></svg>
              }
            </div>
            <span class="text-xs font-bold text-slate-800 group-hover:text-emerald-800"> Exportar Respaldo JSON </span>
            <span class="text-[11px] text-slate-400 mt-1">
              Genera archivos exportables de documentos y fragmentos para respaldo.
            </span>
          </button>
        </div>

        <!-- Integrity Check Results Box -->
        @if (integrityResult(); as integrityResult) {
          <div
            [class]="
              'mt-3 p-4 rounded-xl border text-xs font-mono space-y-1.5 ' +
              (integrityResult.ok
                ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
                : 'bg-red-50/70 border-red-200 text-red-900')
            "
          >
            <div class="flex items-center gap-2 font-bold font-sans">
              @if (integrityResult.ok) {
                <svg [lucide]="icons.CheckCircle2" class="h-4 w-4 text-emerald-600"></svg>
              } @else {
                <svg [lucide]="icons.AlertTriangle" class="h-4 w-4 text-red-600"></svg>
              }
              <span>
                {{
                  integrityResult.ok
                    ? 'Estado: Base de datos RAG íntegra y conectada'
                    : 'Estado: Se encontraron advertencias o errores'
                }}
              </span>
            </div>
            <ul class="list-disc list-inside text-[11px] opacity-90 pl-1 space-y-0.5">
              @for (detail of integrityResult.details; track $index) {
                <li>{{ detail }}</li>
              }
            </ul>
          </div>
        }
      </div>
    </div>
  `,
})
export class KnowledgeBaseSectionComponent {
  private readonly toastService = inject(ToastService)

  protected readonly icons = {
    AlertTriangle,
    CheckCircle2,
    Cpu,
    Database,
    FileDown,
    FolderSync,
    HardDrive,
    Layers,
    RefreshCw,
    Server,
    ShieldCheck,
    Sparkles,
  }

  protected readonly dbInfo = signal<KnowledgePathResponse | null>(null)
  protected readonly isLoading = signal(true)

  // Recovery tools state
  protected readonly integrityLoading = signal(false)
  protected readonly integrityResult = signal<KnowledgeIntegrityResponse | null>(null)
  protected readonly rebuildingIndex = signal(false)
  protected readonly exportingBackup = signal(false)

  protected readonly isPostgres = computed(() => this.dbInfo()?.engine === 'postgresql' || this.dbInfo()?.is_custom)
  protected readonly isConnected = computed(() => this.dbInfo()?.is_accessible !== false)

  constructor() {
    void this.loadStatus()
  }

  protected async loadStatus(): Promise<void> {
    this.isLoading.set(true)
    try {
      const res = await api.getKnowledgePath()
      this.dbInfo.set(res)
    } catch {
      this.toastService.toast.error('No se pudo obtener el estado de la base de conocimiento.')
    } finally {
      this.isLoading.set(false)
    }
  }

  protected async handleCheckIntegrity(): Promise<void> {
    this.integrityLoading.set(true)
    try {
      const res = await api.checkIntegrity()
      this.integrityResult.set(res)
      if (res.ok) {
        this.toastService.toast.success('Integridad del motor RAG verificada correctamente.')
      } else {
        this.toastService.toast.error('Se detectaron advertencias en la base de datos.')
      }
    } catch (err) {
      this.toastService.toast.error(err instanceof Error ? err.message : 'Error al verificar integridad.')
    } finally {
      this.integrityLoading.set(false)
    }
  }

  protected async handleRebuildIndex(): Promise<void> {
    this.rebuildingIndex.set(true)
    try {
      const res = await api.rebuildIndex()
      this.toastService.toast.success(`Índice RAG reconstruido: ${res.chunks_reindexed} fragmentos procesados.`)
      void this.handleCheckIntegrity()
      void this.loadStatus()
    } catch (err) {
      this.toastService.toast.error(err instanceof Error ? err.message : 'Error al reconstruir índice.')
    } finally {
      this.rebuildingIndex.set(false)
    }
  }

  protected async handleExportBackup(): Promise<void> {
    this.exportingBackup.set(true)
    try {
      const res = await api.exportJsonBackup()
      this.toastService.toast.success(
        `Respaldo JSON generado con éxito (${res.manifest_path.split(/[/\\]/).pop()}).`,
      )
    } catch (err) {
      this.toastService.toast.error(err instanceof Error ? err.message : 'Error al exportar respaldo JSON.')
    } finally {
      this.exportingBackup.set(false)
    }
  }
}

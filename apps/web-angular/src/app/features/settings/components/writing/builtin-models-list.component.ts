import { ChangeDetectionStrategy, Component, DestroyRef, inject, input, signal } from '@angular/core'
import { AlertTriangle, CheckCircle2, Cpu, Download, HardDrive, Loader2, RefreshCw, Trash2 } from 'lucide'
import { LucideIconDirective } from '../../../../shared/icons/lucide.directive'
import { detectHardwareProfile, evaluateModel } from '../../../ai/policies/modelSelectionPolicy'
import { getClientWebLLMModels } from '../../../ai/catalogs/clientCatalog'
import type { HardwareProfile, WebLLMInitProgress, WebLLMModelDefinition } from '../../../ai/types/webLlm'
import { formatProgressStage } from '../../../../utils/formatProgressStage'

let webLLMProviderPromise: Promise<
  Awaited<typeof import('../../../ai/providers/WebLLMProvider')>['webLLMProvider']
> | null = null

async function getWebLLMProvider() {
  if (!webLLMProviderPromise) {
    webLLMProviderPromise = import('../../../ai/providers/WebLLMProvider').then((module) => module.webLLMProvider)
  }
  return webLLMProviderPromise
}

/**
 * Port of React `BuiltinModelsList` (WebLLM models cached in the browser).
 * Host is `block` because it is rendered as a direct child of a `space-y-*` form.
 */
@Component({
  selector: 'app-builtin-models-list',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
  template: `
    <div class="space-y-4 pt-2">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h4 class="text-sm font-bold text-slate-900 flex items-center gap-2">
            <svg [lucide]="icons.HardDrive" class="h-4 w-4 text-[#002777]"></svg>
            <span>Modelo en este navegador (WebLLM / WebGPU)</span>
          </h4>
          <p class="text-xs text-slate-500 mt-0.5">
            Modelos de lenguaje ejecutados íntegramente en tu navegador mediante WebLLM y WebGPU. Cero consumo en el
            servidor y total privacidad de datos.
          </p>
        </div>

        <button
          type="button"
          (click)="refreshCacheStatus()"
          [disabled]="isRefreshing()"
          title="Actualizar estado de caché en navegador"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 transition cursor-pointer self-start sm:self-auto disabled:opacity-50"
        >
          <svg [lucide]="icons.RefreshCw" [class]="'h-3.5 w-3.5 ' + (isRefreshing() ? 'animate-spin' : '')"></svg>
          <span>Actualizar</span>
        </button>
      </div>

      @if (hardware() && !hardware()!.hasWebGPU) {
        <div
          class="p-3.5 rounded-xl bg-amber-50 border border-amber-200 flex items-start gap-2.5 text-xs text-amber-800"
        >
          <svg [lucide]="icons.AlertTriangle" class="h-4 w-4 text-amber-600 shrink-0 mt-0.5"></svg>
          <div>
            <span class="font-semibold block">Aceleración WebGPU no detectada</span>
            <span>
              Tu navegador o hardware no tiene WebGPU activo. Te sugerimos seleccionar una API externa (Groq, OpenAI,
              Gemini, Claude u Ollama Remoto).
            </span>
          </div>
        </div>
      }

      @if (hardware(); as hw) {
        @if (hw.hasWebGPU) {
          <div
            class="p-3 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between text-xs text-slate-700"
          >
            <div class="flex items-center gap-2">
              <svg [lucide]="icons.Cpu" class="h-4 w-4 text-[#002777]"></svg>
              <span>Dispositivo: <strong class="font-semibold text-slate-900">{{ hw.adapterName }}</strong></span>
            </div>
            <span
              class="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200"
            >
              <svg [lucide]="icons.CheckCircle2" class="h-3 w-3 text-emerald-600"></svg>
              WebGPU Activo ({{ hw.hasShaderF16 ? 'shader-f16 compatible' : 'shader estándar' }})
            </span>
          </div>
        }
      }

      <div class="space-y-3">
        @for (m of modelsList(); track m.id) {
          @let isDownloaded = !!cachedMap()[m.id];
          @let isSelected = model() === m.id;
          @let isDownloading = downloadingId() === m.id;
          @let isDeleting = deletingId() === m.id;
          @let progressInfo = progressState()[m.id];
          @let evaluation = hardware() ? evaluateModel(m, hardware()!, 'balanced') : null;
          <div
            (click)="setModel()(m.id)"
            [class]="
              'flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl transition-all cursor-pointer ' +
              (isSelected
                ? 'border-2 border-[#002777] bg-blue-50/20 shadow-xs'
                : 'border border-slate-200 bg-white hover:border-slate-300')
            "
          >
            <div class="space-y-1.5 flex-1 min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h5 class="font-bold text-slate-900 text-base">{{ m.name }}</h5>
                @if (isDownloaded) {
                  <span
                    class="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-200"
                  >
                    <span class="h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                    En caché del navegador
                  </span>
                } @else {
                  <span
                    class="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500 border border-slate-200"
                  >
                    No descargado ({{ m.downloadSize }})
                  </span>
                }
                @if (isSelected) {
                  <span class="rounded-md bg-blue-100 px-2 py-0.5 text-xs font-semibold text-[#002777]">
                    Seleccionado
                  </span>
                }
                @if (evaluation?.isRecommended) {
                  <span
                    class="rounded-md bg-purple-50 px-2 py-0.5 text-xs font-semibold text-purple-700 border border-purple-200"
                  >
                    Recomendado para tu equipo
                  </span>
                }
              </div>

              <p class="text-xs text-slate-600 leading-relaxed max-w-2xl">{{ m.description }}</p>

              <p class="text-xs text-slate-400 font-medium pt-0.5 flex flex-wrap items-center gap-2">
                <span>Descarga: {{ m.downloadSize }}</span>
                <span>•</span>
                <span>VRAM estimada: {{ m.vramFormatted }}</span>
                <span>•</span>
                <span>Ventana: {{ m.contextWindow }}</span>
              </p>

              @if (isDownloading && progressInfo) {
                <div class="pt-2 space-y-1.5">
                  <div class="flex justify-between text-xs font-semibold text-slate-700">
                    <span>{{ formatProgressStage(progressInfo.text, progressInfo.progress) }}</span>
                    <span>{{ progressInfo.progress }}%</span>
                  </div>
                  <div class="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                    <div
                      class="bg-[#002777] h-2 rounded-full transition-all duration-300"
                      [style.width]="progressInfo.progress + '%'"
                    ></div>
                  </div>
                </div>
              }
            </div>

            <div class="shrink-0 flex items-center gap-2" (click)="$event.stopPropagation()">
              @if (isDownloaded) {
                <button
                  type="button"
                  [disabled]="isDeleting || isDownloading"
                  (click)="handleDelete(m.id)"
                  title="Eliminar modelo de la caché del navegador"
                  class="inline-flex items-center gap-1 px-3 py-2 rounded-xl text-xs font-semibold text-red-600 bg-red-50 hover:bg-red-100 border border-red-200 transition cursor-pointer disabled:opacity-50"
                >
                  @if (isDeleting) {
                    <svg [lucide]="icons.Loader2" class="h-3.5 w-3.5 animate-spin"></svg>
                  } @else {
                    <svg [lucide]="icons.Trash2" class="h-3.5 w-3.5"></svg>
                  }
                  Liberar caché
                </button>

                <button
                  type="button"
                  (click)="setModel()(m.id)"
                  [class]="
                    'px-4 py-2 rounded-xl text-xs font-semibold transition cursor-pointer ' +
                    (isSelected
                      ? 'bg-[#002777] text-white font-bold'
                      : 'border border-slate-200 bg-white hover:bg-slate-50 text-slate-700')
                  "
                >
                  {{ isSelected ? 'Activo' : 'Seleccionar' }}
                </button>
              } @else {
                <button
                  type="button"
                  [disabled]="isDownloading"
                  (click)="handleDownload(m)"
                  class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-blue-50 text-[#002777] hover:bg-blue-100 border border-blue-200 transition cursor-pointer disabled:opacity-50"
                >
                  @if (isDownloading) {
                    <svg [lucide]="icons.Loader2" class="h-3.5 w-3.5 animate-spin"></svg>
                    <span>Descargando {{ progressInfo ? '(' + progressInfo.progress + '%)' : '...' }}</span>
                  } @else {
                    <svg [lucide]="icons.Download" class="h-3.5 w-3.5"></svg>
                    <span>Descargar ({{ m.downloadSize }})</span>
                  }
                </button>
              }
            </div>
          </div>
        }
      </div>
    </div>
  `,
})
export class BuiltinModelsListComponent {
  readonly model = input.required<string>()
  readonly setModel = input.required<(m: string) => void>()

  protected readonly icons = { AlertTriangle, CheckCircle2, Cpu, Download, HardDrive, Loader2, RefreshCw, Trash2 }
  protected readonly evaluateModel = evaluateModel
  protected readonly formatProgressStage = formatProgressStage

  protected readonly cachedMap = signal<Record<string, boolean>>({})
  protected readonly hardware = signal<HardwareProfile | null>(null)
  protected readonly downloadingId = signal<string | null>(null)
  protected readonly deletingId = signal<string | null>(null)
  protected readonly progressState = signal<Record<string, WebLLMInitProgress>>({})
  protected readonly isRefreshing = signal(false)

  constructor() {
    let isMounted = true
    inject(DestroyRef).onDestroy(() => {
      isMounted = false
    })
    void detectHardwareProfile()
      .then((profile) => {
        if (isMounted) this.hardware.set(profile)
      })
      .catch((err) => {
        console.warn('Hardware profile detection failed:', err)
      })

    void this.refreshCacheStatus()
  }

  /** React read `getClientWebLLMModels()` on every render; the runtime catalog is a module-level list. */
  protected modelsList(): readonly WebLLMModelDefinition[] {
    return getClientWebLLMModels()
  }

  protected async refreshCacheStatus(): Promise<void> {
    this.isRefreshing.set(true)
    try {
      const provider = await getWebLLMProvider()
      const nextMap: Record<string, boolean> = {}
      for (const m of getClientWebLLMModels()) {
        nextMap[m.id] = await provider.isModelCached(m.id)
      }
      this.cachedMap.set(nextMap)
    } finally {
      this.isRefreshing.set(false)
    }
  }

  protected async handleDownload(modelDef: WebLLMModelDefinition): Promise<void> {
    this.downloadingId.set(modelDef.id)
    this.progressState.update((prev) => ({
      ...prev,
      [modelDef.id]: { progress: 0, text: 'Iniciando descarga en caché del navegador...', timeElapsed: 0 },
    }))

    try {
      const provider = await getWebLLMProvider()
      await provider.initModel(modelDef.id, (report) => {
        this.progressState.update((prev) => ({
          ...prev,
          [modelDef.id]: report,
        }))
      })
      await this.refreshCacheStatus()
      this.setModel()(modelDef.id)
    } catch (err) {
      console.error(`Error inicializando modelo ${modelDef.id}:`, err)
    } finally {
      this.downloadingId.set(null)
    }
  }

  protected async handleDelete(modelId: string): Promise<void> {
    this.deletingId.set(modelId)
    try {
      const provider = await getWebLLMProvider()
      await provider.deleteCachedModel(modelId)
      await this.refreshCacheStatus()
    } catch (err) {
      console.error(`Error eliminando modelo ${modelId}:`, err)
    } finally {
      this.deletingId.set(null)
    }
  }
}

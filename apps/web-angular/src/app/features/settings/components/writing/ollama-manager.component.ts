import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core'
import { CheckCircle2, RefreshCw, Server, XCircle } from 'lucide'
import { LucideIconDirective } from '../../../../shared/icons/lucide.directive'
import { validateRemoteEndpointUrl, type ValidationResult } from '../../validators/settingsValidation'

/**
 * Port of React `OllamaManager`.
 * Host is `block` because it is rendered as a direct child of a `space-y-*` form.
 */
@Component({
  selector: 'app-ollama-manager',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
  template: `
    <div class="space-y-4 bg-slate-50 p-4 rounded-xl border border-slate-200">
      <div class="flex items-center justify-between">
        <label class="text-xs font-bold text-slate-800 flex items-center gap-2">
          <svg [lucide]="icons.Server" class="h-4 w-4 text-[#002777]"></svg>
          <span>Servidor Ollama Remoto (HTTPS Externo)</span>
        </label>
        <button
          type="button"
          (click)="setShowEndpointSection()(!showEndpointSection())"
          class="text-xs text-[#002777] font-semibold hover:underline cursor-pointer"
        >
          {{ showEndpointSection() ? 'Ocultar Configuración de URL' : 'Configurar URL de Ollama Remoto' }}
        </button>
      </div>

      <p class="text-xs text-slate-500">
        Conéctate a una instancia remota de Ollama alojada fuera de esta máquina. Por seguridad y aislamiento, no se
        admiten conexiones a localhost ni a redes privadas.
      </p>

      @if (showEndpointSection()) {
        <div class="space-y-2 pt-1 border-t border-slate-200">
          <label class="text-[11px] font-semibold text-slate-700 block">
            Endpoint URL de Ollama Remoto (HTTPS obligatorio)
          </label>
          <div class="flex gap-2">
            <input
              type="text"
              [value]="ollamaUrl()"
              (input)="setOllamaUrl()($any($event.target).value)"
              placeholder="https://ollama.tu-dominio.com"
              class="input-field text-xs font-mono py-1.5 border border-slate-200 rounded-xl flex-1"
            />
            <button
              type="button"
              [disabled]="fetchingModels() || !ollamaUrl().trim() || !urlValidation().isValid"
              (click)="fetchOllamaModels()(ollamaUrl(), true)"
              class="btn btn-secondary text-xs py-1.5 px-3 shrink-0 inline-flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              <svg [lucide]="icons.RefreshCw" [class]="'h-3.5 w-3.5 ' + (fetchingModels() ? 'animate-spin' : '')"></svg>
              <span>Verificar Conexión</span>
            </button>
          </div>
          @if (!urlValidation().isValid && urlValidation().error) {
            <p class="text-[11px] text-red-600 font-medium">{{ urlValidation().error }}</p>
          }
        </div>
      }

      <div class="flex items-center justify-between text-xs pt-1">
        <span class="text-slate-600 font-medium">Estado del Servicio Remoto:</span>
        @if (fetchingModels()) {
          <span class="inline-flex items-center gap-1 text-slate-500 font-medium">
            <svg [lucide]="icons.RefreshCw" class="h-3.5 w-3.5 animate-spin"></svg> Verificando conexión...
          </span>
        } @else if (ollamaOnline() === true) {
          <span
            class="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full font-bold text-[11px]"
          >
            <svg [lucide]="icons.CheckCircle2" class="h-3.5 w-3.5"></svg> En línea ({{ ollamaModels().length }} modelos
            remotos disponibles)
          </span>
        } @else {
          <span
            class="inline-flex items-center gap-1 text-slate-600 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-full font-medium text-[11px]"
          >
            <svg [lucide]="icons.XCircle" class="h-3.5 w-3.5 text-slate-400"></svg> Sin conexión
          </span>
        }
      </div>

      @if (ollamaOnline() && ollamaModels().length > 0) {
        <div class="space-y-1.5 pt-1">
          <label class="text-xs font-bold text-slate-800 block">
            Seleccionar Modelo Expuesto por el Servidor Remoto
          </label>
          <select
            (change)="setModel()($any($event.target).value)"
            class="input-field text-xs font-mono py-2 bg-white border border-slate-200 rounded-xl w-full"
          >
            @for (m of ollamaModels(); track m) {
              <option [value]="m" [selected]="m === model()">{{ m }}</option>
            }
          </select>
        </div>
      }
    </div>
  `,
})
export class OllamaManagerComponent {
  readonly model = input.required<string>()
  readonly setModel = input.required<(m: string) => void>()
  readonly showEndpointSection = input.required<boolean>()
  readonly setShowEndpointSection = input.required<(show: boolean) => void>()
  readonly ollamaUrl = input.required<string>()
  readonly setOllamaUrl = input.required<(url: string) => void>()
  readonly ollamaOnline = input.required<boolean | null>()
  readonly ollamaModels = input.required<string[]>()
  readonly fetchingModels = input.required<boolean>()
  readonly fetchOllamaModels = input.required<(url?: string, isUserAction?: boolean) => Promise<void>>()

  protected readonly icons = { CheckCircle2, RefreshCw, Server, XCircle }

  protected readonly urlValidation = computed<ValidationResult>(() =>
    this.ollamaUrl().trim() ? validateRemoteEndpointUrl(this.ollamaUrl(), false) : { isValid: true },
  )
}

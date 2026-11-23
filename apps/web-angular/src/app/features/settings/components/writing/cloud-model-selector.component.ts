import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core'
import type { AISettings, ModelCatalogItem } from '../../../../api/client'
import { ApiKeyInputComponent } from './api-key-input.component'

/**
 * Port of React `CloudModelSelector`.
 * Host is `block` because it is rendered as a direct child of a `space-y-*` form.
 */
@Component({
  selector: 'app-cloud-model-selector',
  imports: [ApiKeyInputComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
  template: `
    <div class="space-y-4 pt-1">
      @if (provider() === 'groq') {
        <app-api-key-input
          label="Clave API"
          [value]="groqKey()"
          (onChange)="setGroqKey()($event)"
          [showKey]="showKey()"
          [setShowKey]="setShowKey()"
          [hasSavedKey]="!!ai()?.groq_api_key_set"
          placeholder="gsk_..."
        />
      }

      @if (provider() === 'gemini') {
        <app-api-key-input
          label="Clave API"
          [value]="geminiKey()"
          (onChange)="setGeminiKey()($event)"
          [showKey]="showKey()"
          [setShowKey]="setShowKey()"
          [hasSavedKey]="!!ai()?.gemini_api_key_set"
          placeholder="AIzaSy..."
        />
      }

      @if (provider() === 'openai') {
        <app-api-key-input
          label="Clave API"
          [value]="openaiKey()"
          (onChange)="setOpenaiKey()($event)"
          [showKey]="showKey()"
          [setShowKey]="setShowKey()"
          [hasSavedKey]="!!ai()?.openai_api_key_set"
          placeholder="sk-..."
        />
      }

      @if (provider() === 'claude') {
        <app-api-key-input
          label="Clave API"
          [value]="claudeKey()"
          (onChange)="setClaudeKey()($event)"
          [showKey]="showKey()"
          [setShowKey]="setShowKey()"
          [hasSavedKey]="!!ai()?.claude_api_key_set"
          placeholder="sk-ant-..."
        />
      }

      <!-- Lista de Modelos Cloud con diseño idéntico al de modelos Built-in -->
      <div class="space-y-3 pt-2">
        @for (cm of cloudModelsForProvider(); track cm.id) {
          @let isSelected = isModelSelected(cm);
          <div
            (click)="setModel()(cm.raw_id || cm.id)"
            [class]="
              'flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl transition-all cursor-pointer select-none ' +
              (isSelected
                ? 'border-2 border-[#002777] bg-blue-50/20 shadow-xs'
                : 'border border-slate-200 bg-white hover:border-slate-300')
            "
          >
            <div class="space-y-1.5 flex-1 min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h5 class="font-bold text-slate-900 text-base">{{ cm.name }}</h5>
                @if (isSelected) {
                  <span class="rounded-md bg-blue-100 px-2 py-0.5 text-xs font-semibold text-[#002777]">
                    Seleccionado
                  </span>
                }
              </div>

              @if (cm.description) {
                <p class="text-xs text-slate-600 leading-relaxed max-w-2xl">{{ cm.description }}</p>
              }

              <p class="text-xs text-slate-400 font-medium pt-0.5 flex flex-wrap items-center gap-2">
                <span>Ventana de Contexto: {{ cm.context_window }}</span>
                @if (cm.max_output_tokens) {
                  <span>•</span>
                  <span>Salida máx: {{ cm.max_output_tokens.toLocaleString() }} tokens</span>
                }
                <span>•</span>
                <span>Precios: {{ cm.pricing_label }}</span>
                @if (cm.rate_limits) {
                  <span>•</span>
                  <span>Límites: {{ cm.rate_limits }}</span>
                }
              </p>
            </div>
          </div>
        }
      </div>
    </div>
  `,
})
export class CloudModelSelectorComponent {
  readonly provider = input.required<string>()
  readonly model = input.required<string>()
  readonly setModel = input.required<(m: string) => void>()
  readonly catalogModels = input.required<ModelCatalogItem[]>()
  readonly ai = input.required<AISettings | null>()
  readonly groqKey = input.required<string>()
  readonly setGroqKey = input.required<(k: string) => void>()
  readonly geminiKey = input.required<string>()
  readonly setGeminiKey = input.required<(k: string) => void>()
  readonly openaiKey = input.required<string>()
  readonly setOpenaiKey = input.required<(k: string) => void>()
  readonly claudeKey = input.required<string>()
  readonly setClaudeKey = input.required<(k: string) => void>()
  readonly showKey = input.required<boolean>()
  readonly setShowKey = input.required<(show: boolean) => void>()

  protected readonly cloudModelsForProvider = computed(() =>
    this.catalogModels().filter((cm) => cm.provider === this.provider() && cm.task_type === 'chat_writing'),
  )

  protected isModelSelected(cm: ModelCatalogItem): boolean {
    const model = this.model()
    return Boolean(
      model === cm.id ||
        model === cm.raw_id ||
        (cm.raw_id && model.endsWith(cm.raw_id)) ||
        (cm.id && model.endsWith(cm.id)),
    )
  }
}

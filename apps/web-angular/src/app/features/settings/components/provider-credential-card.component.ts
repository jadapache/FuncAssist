import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  afterRenderEffect,
  computed,
  input,
  signal,
  untracked,
  viewChild,
} from '@angular/core'
import { AlertTriangle, CheckCircle2, Eye, EyeOff, Key, Play, RefreshCw, Shield, Trash2 } from 'lucide'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'
import type { ProviderCredentialInfo } from '../types'

/**
 * Port of React `ProviderCredentialCard`.
 * `onSave` / `onTest` / `onDelete` are awaited by the card (busy state), so they stay function inputs.
 */
@Component({
  selector: 'app-provider-credential-card',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-xs transition hover:border-slate-300">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
        <div class="flex items-center gap-3">
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-[#002777]">
            <svg [lucide]="icons.Key" class="h-5 w-5"></svg>
          </div>
          <div>
            <h4 class="text-sm font-bold text-slate-900">{{ label() }}</h4>
            <p class="text-xs text-slate-500">{{ description() }}</p>
          </div>
        </div>

        <div>
          @if (isConfigured()) {
            @if (hasError()) {
              <span
                class="inline-flex items-center gap-1.5 rounded-full bg-red-50 border border-red-200 px-2.5 py-1 text-xs font-semibold text-red-700"
              >
                <svg [lucide]="icons.AlertTriangle" class="h-3.5 w-3.5 text-red-500"></svg>
                <span>Error de validación</span>
              </span>
            } @else if (isValid()) {
              <span
                class="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-1 text-xs font-semibold text-emerald-700"
              >
                <svg [lucide]="icons.CheckCircle2" class="h-3.5 w-3.5 text-emerald-600"></svg>
                <span>Configurada y Activa</span>
              </span>
            } @else {
              <span
                class="inline-flex items-center gap-1.5 rounded-full bg-blue-50 border border-blue-200 px-2.5 py-1 text-xs font-semibold text-blue-700"
              >
                <svg [lucide]="icons.Shield" class="h-3.5 w-3.5 text-blue-600"></svg>
                <span>Configurada</span>
              </span>
            }
          } @else {
            <span
              class="inline-flex items-center gap-1.5 rounded-full bg-slate-100 border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600"
            >
              Pendiente de configurar
            </span>
          }
        </div>
      </div>

      @if (credential()?.validation_error) {
        <div class="mb-3 rounded-lg bg-red-50 border border-red-200 p-2.5 text-xs text-red-800">
          {{ credential()?.validation_error }}
        </div>
      }

      @if (isEditing() || !isConfigured()) {
        <div class="space-y-3 pt-2">
          <div class="relative">
            <input
              #keyInput
              [type]="showKey() ? 'text' : 'password'"
              [value]="apiKeyInput()"
              (input)="apiKeyInput.set($any($event.target).value)"
              [placeholder]="isConfigured() ? '•••••••••••••••• (Introduce nueva clave)' : 'Pega tu API Key personal aquí'"
              class="w-full px-3 py-2 pr-10 text-xs font-mono text-slate-900 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              (keydown)="$event.key === 'Enter' && handleSave()"
            />
            <button
              type="button"
              (click)="showKey.set(!showKey())"
              class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-1 cursor-pointer"
              [title]="showKey() ? 'Ocultar' : 'Mostrar'"
            >
              @if (showKey()) {
                <svg [lucide]="icons.EyeOff" class="h-4 w-4"></svg>
              } @else {
                <svg [lucide]="icons.Eye" class="h-4 w-4"></svg>
              }
            </button>
          </div>

          <div class="flex items-center gap-2">
            <button
              type="button"
              (click)="handleSave()"
              [disabled]="busy() || !apiKeyInput().trim()"
              class="px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold disabled:opacity-50 cursor-pointer shadow-xs transition"
            >
              {{ busy() ? 'Guardando...' : isConfigured() ? 'Actualizar clave' : 'Guardar clave' }}
            </button>
            @if (isConfigured()) {
              <button
                type="button"
                (click)="apiKeyInput.set(''); isEditing.set(false)"
                class="px-3 py-1.5 rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 text-xs font-medium cursor-pointer transition"
              >
                Cancelar
              </button>
            }
          </div>
        </div>
      } @else {
        <div class="flex flex-wrap items-center justify-between gap-3 pt-2">
          <div class="text-xs text-slate-500 font-mono">Clave guardada y cifrada en AES-256.</div>
          <div class="flex items-center gap-2">
            <button
              type="button"
              (click)="handleTest()"
              [disabled]="busy()"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold cursor-pointer transition"
              title="Probar credencial"
            >
              <svg [lucide]="icons.Play" class="h-3.5 w-3.5 text-slate-600"></svg>
              <span>{{ busy() ? 'Validando...' : 'Probar' }}</span>
            </button>
            <button
              type="button"
              (click)="isEditing.set(true)"
              [disabled]="busy()"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-semibold cursor-pointer transition"
            >
              <svg [lucide]="icons.RefreshCw" class="h-3.5 w-3.5"></svg>
              <span>Reemplazar</span>
            </button>
            <button
              type="button"
              (click)="handleDelete()"
              [disabled]="busy()"
              class="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 transition cursor-pointer"
              title="Eliminar credencial"
            >
              <svg [lucide]="icons.Trash2" class="h-4 w-4"></svg>
            </button>
          </div>
        </div>
      }
    </div>
  `,
})
export class ProviderCredentialCardComponent {
  readonly provider = input.required<string>()
  readonly label = input.required<string>()
  readonly description = input.required<string>()
  readonly credential = input<ProviderCredentialInfo | undefined>(undefined)
  readonly onSave = input.required<(apiKey: string) => Promise<void>>()
  readonly onTest = input.required<() => Promise<void>>()
  readonly onDelete = input.required<() => Promise<void>>()

  protected readonly icons = { AlertTriangle, CheckCircle2, Eye, EyeOff, Key, Play, RefreshCw, Shield, Trash2 }

  protected readonly apiKeyInput = signal('')
  protected readonly showKey = signal(false)
  protected readonly isEditing = signal(false)
  protected readonly busy = signal(false)

  protected readonly isConfigured = computed(() => {
    const credential = this.credential()
    return Boolean(
      credential?.is_configured ?? credential?.configured ?? (credential?.status && credential.status !== 'unconfigured'),
    )
  })
  protected readonly isValid = computed(() => this.credential()?.is_valid ?? this.credential()?.status === 'active')
  protected readonly hasError = computed(() => {
    const credential = this.credential()
    return Boolean(
      credential?.validation_error || credential?.status === 'validation_failed' || credential?.status === 'error',
    )
  })

  private readonly keyInput = viewChild<ElementRef<HTMLInputElement>>('keyInput')

  constructor() {
    // React `autoFocus={isEditing}`: focus the key input when it mounts while editing.
    afterRenderEffect(() => {
      const el = this.keyInput()
      if (el && untracked(this.isEditing)) el.nativeElement.focus()
    })
  }

  protected async handleSave(): Promise<void> {
    if (!this.apiKeyInput().trim()) return
    this.busy.set(true)
    try {
      await this.onSave()(this.apiKeyInput().trim())
      this.apiKeyInput.set('')
      this.isEditing.set(false)
    } finally {
      this.busy.set(false)
    }
  }

  protected async handleTest(): Promise<void> {
    this.busy.set(true)
    try {
      await this.onTest()()
    } finally {
      this.busy.set(false)
    }
  }

  protected async handleDelete(): Promise<void> {
    if (!window.confirm(`¿Seguro que deseas eliminar la API Key de ${this.label()}?`)) return
    this.busy.set(true)
    try {
      await this.onDelete()()
      this.apiKeyInput.set('')
      this.isEditing.set(false)
    } finally {
      this.busy.set(false)
    }
  }
}

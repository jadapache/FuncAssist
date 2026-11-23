import { ChangeDetectionStrategy, Component, input, signal } from '@angular/core'
import { AlertTriangle, Check, CheckCircle2, Play, Plus, RefreshCw, Server, Terminal, Trash2, X } from 'lucide'
import { LucideIconDirective } from '../../../shared/icons/lucide.directive'
import type { McpServerInfo, McpServerPayload } from '../types'

/**
 * Port of React `MCPServersSection`.
 * The `onAddServer` / `onUpdateServer` / `onDeleteServer` / `onTestServer` callbacks return promises that
 * the section awaits (busy state, form reset), so they stay function inputs with the same names.
 */
@Component({
  selector: 'app-mcp-servers-section',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div class="rounded-2xl border border-slate-200 bg-white p-6 md:p-8 shadow-sm space-y-6">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div class="flex items-center gap-3">
          <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-purple-50 text-purple-700">
            <svg [lucide]="icons.Server" class="h-6 w-6"></svg>
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h3 class="text-lg font-bold text-slate-900">Model Context Protocol (MCP)</h3>
              <span
                class="inline-flex items-center text-[10px] font-bold text-purple-700 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full uppercase tracking-wider"
              >
                Extensible
              </span>
            </div>
            <p class="text-xs text-slate-500 mt-0.5">
              Conecta servidores y herramientas externas de contexto (SSE, HTTP) validados contra SSRF.
            </p>
          </div>
        </div>

        @if (!isAdding()) {
          <button
            type="button"
            (click)="resetForm(); isAdding.set(true)"
            [disabled]="loading() || busy()"
            class="px-3.5 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold cursor-pointer shadow-xs transition flex items-center gap-1.5 self-start sm:self-auto"
          >
            <svg [lucide]="icons.Plus" class="h-4 w-4"></svg>
            <span>Añadir Servidor MCP</span>
          </button>
        }
      </div>

      @if (isAdding()) {
        <div class="rounded-xl border border-blue-200 bg-blue-50/30 p-5 space-y-4">
          <div class="flex items-center justify-between">
            <h4 class="text-sm font-bold text-slate-900 flex items-center gap-2">
              <svg [lucide]="icons.Terminal" class="h-4 w-4 text-blue-600"></svg>
              <span>{{ editingId() ? 'Editar Servidor MCP' : 'Registrar Nuevo Servidor MCP' }}</span>
            </h4>
            <button type="button" (click)="resetForm()" class="text-slate-400 hover:text-slate-600 p-1 cursor-pointer">
              <svg [lucide]="icons.X" class="h-4 w-4"></svg>
            </button>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="text-xs font-semibold text-slate-700 block mb-1"> Nombre del Servidor * </label>
              <input
                type="text"
                [value]="name()"
                (input)="name.set($any($event.target).value)"
                placeholder="p. ej. Servidor de Documentación"
                class="w-full px-3 py-2 text-xs text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </div>

            <div>
              <label class="text-xs font-semibold text-slate-700 block mb-1"> Descripción (opcional) </label>
              <input
                type="text"
                [value]="description()"
                (input)="description.set($any($event.target).value)"
                placeholder="Herramientas de búsqueda y lectura de archivos"
                class="w-full px-3 py-2 text-xs text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </div>

            <div class="sm:col-span-2">
              <label class="text-xs font-semibold text-slate-700 block mb-1"> URL del Endpoint MCP * </label>
              <input
                type="url"
                [value]="endpointUrl()"
                (input)="endpointUrl.set($any($event.target).value)"
                placeholder="https://mcp-server.empresa.com/sse"
                class="w-full px-3 py-2 text-xs font-mono text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
              <p class="text-[11px] text-slate-500 mt-1">
                Por seguridad SSRF, el endpoint debe ser HTTPS/HTTP público válido (se bloquean IPs privadas y metadatos
                cloud).
              </p>
            </div>

            <div>
              <label class="text-xs font-semibold text-slate-700 block mb-1"> Transporte </label>
              <select
                [value]="transportType()"
                (change)="transportType.set($any($event.target).value)"
                class="w-full px-3 py-2 text-xs text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              >
                <option value="sse">Server-Sent Events (SSE)</option>
                <option value="http">HTTP POST / Stream</option>
              </select>
            </div>

            <div>
              <label class="text-xs font-semibold text-slate-700 block mb-1"> Autenticación </label>
              <select
                [value]="authType()"
                (change)="authType.set($any($event.target).value)"
                class="w-full px-3 py-2 text-xs text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              >
                <option value="none">Sin autenticación (Público)</option>
                <option value="bearer">Bearer Token</option>
                <option value="api_key">Header API Key</option>
              </select>
            </div>

            @if (authType() !== 'none') {
              <div class="sm:col-span-2">
                <label class="text-xs font-semibold text-slate-700 block mb-1"> Secreto / Token de Autenticación </label>
                <input
                  type="password"
                  [value]="authSecret()"
                  (input)="authSecret.set($any($event.target).value)"
                  [placeholder]="editingId() ? '•••••••••••••••• (dejar en blanco para mantener)' : 'Secreto'"
                  class="w-full px-3 py-2 text-xs font-mono text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
                />
              </div>
            }

            <div class="sm:col-span-2">
              <label class="text-xs font-semibold text-slate-700 block mb-1">
                Herramientas Permitidas (Separadas por comas, o * para todas)
              </label>
              <input
                type="text"
                [value]="toolsInput()"
                (input)="toolsInput.set($any($event.target).value)"
                placeholder="*, search_docs, read_file"
                class="w-full px-3 py-2 text-xs font-mono text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </div>
          </div>

          <div class="flex items-center gap-2 pt-2">
            <button
              type="button"
              (click)="handleSubmit()"
              [disabled]="busy() || !name().trim() || !endpointUrl().trim()"
              class="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold disabled:opacity-50 cursor-pointer shadow-xs transition flex items-center gap-1.5"
            >
              <svg [lucide]="icons.Check" class="h-4 w-4"></svg>
              <span>{{ busy() ? 'Guardando...' : editingId() ? 'Actualizar Servidor' : 'Registrar Servidor' }}</span>
            </button>
            <button
              type="button"
              (click)="resetForm()"
              class="px-3 py-2 rounded-xl bg-slate-100 text-slate-600 hover:bg-slate-200 text-xs font-medium cursor-pointer transition"
            >
              Cancelar
            </button>
          </div>
        </div>
      }

      <!-- Lista de Servidores -->
      @if (servers().length === 0) {
        <div class="rounded-xl border border-dashed border-slate-200 p-8 text-center space-y-2">
          <div class="flex justify-center text-slate-300">
            <svg [lucide]="icons.Server" class="h-10 w-10 stroke-1"></svg>
          </div>
          <h4 class="text-sm font-semibold text-slate-800">No tienes servidores MCP configurados</h4>
          <p class="text-xs text-slate-500 max-w-md mx-auto">
            Puedes conectar servidores externos que cumplan la especificación Model Context Protocol para proporcionar
            herramientas a los agentes de FuncAssist.
          </p>
        </div>
      } @else {
        <div class="space-y-3">
          @for (s of servers(); track s.id) {
            <div
              class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50/60 p-4 transition hover:bg-slate-50"
            >
              <div class="space-y-1.5 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="text-sm font-bold text-slate-900 truncate">{{ s.name }}</span>
                  <span
                    class="px-2 py-0.5 text-[10px] font-bold rounded-md bg-white border border-slate-200 text-slate-600 uppercase"
                  >
                    {{ s.transport_type }}
                  </span>

                  @if (s.status === 'connected') {
                    <span
                      class="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full"
                    >
                      <svg [lucide]="icons.CheckCircle2" class="h-3 w-3 text-emerald-600"></svg>
                      <span>Conectado</span>
                    </span>
                  } @else if (s.status === 'disabled') {
                    <span
                      class="inline-flex items-center text-[11px] font-medium text-slate-500 bg-slate-200 border border-slate-300 px-2.5 py-0.5 rounded-full"
                    >
                      Desactivado
                    </span>
                  } @else if (s.status === 'error') {
                    <span
                      class="inline-flex items-center gap-1 text-[11px] font-semibold text-red-700 bg-red-50 border border-red-200 px-2.5 py-0.5 rounded-full"
                    >
                      <svg [lucide]="icons.AlertTriangle" class="h-3 w-3 text-red-600"></svg>
                      <span>Error</span>
                    </span>
                  } @else {
                    <span
                      class="inline-flex items-center text-[11px] font-medium text-blue-700 bg-blue-50 border border-blue-200 px-2.5 py-0.5 rounded-full"
                    >
                      Configurado
                    </span>
                  }
                </div>

                @if (s.description) {
                  <p class="text-xs text-slate-500">{{ s.description }}</p>
                }

                <div class="flex items-center gap-3 text-xs text-slate-400 font-mono pt-1">
                  <span class="truncate max-w-sm">{{ s.endpoint_url }}</span>
                  @if (s.allowed_tools && s.allowed_tools.length > 0) {
                    <span class="text-[11px] text-purple-700 bg-purple-50 px-2 py-0.5 rounded-md font-sans font-medium">
                      {{ s.allowed_tools.length }} herramienta(s)
                    </span>
                  }
                </div>
              </div>

              <div class="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  (click)="onTestServer()(s.id)"
                  [disabled]="busy()"
                  class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 text-xs font-semibold cursor-pointer transition"
                  title="Probar conectividad del servidor"
                >
                  <svg [lucide]="icons.Play" class="h-3.5 w-3.5 text-slate-600"></svg>
                  <span>Probar</span>
                </button>

                <button
                  type="button"
                  (click)="handleToggleStatus(s)"
                  [disabled]="busy()"
                  class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 text-xs font-semibold cursor-pointer transition"
                >
                  <span>{{ s.status === 'disabled' ? 'Habilitar' : 'Deshabilitar' }}</span>
                </button>

                <button
                  type="button"
                  (click)="handleStartEdit(s)"
                  [disabled]="busy()"
                  class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 text-blue-700 hover:bg-blue-50 text-xs font-semibold cursor-pointer transition"
                >
                  <svg [lucide]="icons.RefreshCw" class="h-3.5 w-3.5"></svg>
                  <span>Editar</span>
                </button>

                <button
                  type="button"
                  (click)="handleDelete(s.id, s.name)"
                  [disabled]="busy()"
                  class="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 transition cursor-pointer"
                  title="Eliminar servidor"
                >
                  <svg [lucide]="icons.Trash2" class="h-4 w-4"></svg>
                </button>
              </div>
            </div>
          }
        </div>
      }
    </div>
  `,
})
export class MCPServersSectionComponent {
  readonly servers = input.required<McpServerInfo[]>()
  readonly loading = input.required<boolean>()
  readonly onAddServer = input.required<(payload: McpServerPayload) => Promise<void>>()
  readonly onUpdateServer =
    input.required<(id: string, payload: Partial<McpServerPayload & { status?: string }>) => Promise<void>>()
  readonly onDeleteServer = input.required<(id: string) => Promise<void>>()
  readonly onTestServer = input.required<(id: string) => Promise<void>>()

  protected readonly icons = { AlertTriangle, Check, CheckCircle2, Play, Plus, RefreshCw, Server, Terminal, Trash2, X }

  protected readonly isAdding = signal(false)
  protected readonly editingId = signal<string | null>(null)
  protected readonly busy = signal(false)

  // Form State
  protected readonly name = signal('')
  protected readonly description = signal('')
  protected readonly endpointUrl = signal('')
  protected readonly transportType = signal('sse')
  protected readonly authType = signal('none')
  protected readonly authSecret = signal('')
  protected readonly toolsInput = signal('')

  protected resetForm(): void {
    this.name.set('')
    this.description.set('')
    this.endpointUrl.set('')
    this.transportType.set('sse')
    this.authType.set('none')
    this.authSecret.set('')
    this.toolsInput.set('')
    this.isAdding.set(false)
    this.editingId.set(null)
  }

  protected handleStartEdit(server: McpServerInfo): void {
    this.editingId.set(server.id)
    this.name.set(server.name)
    this.description.set(server.description || '')
    this.endpointUrl.set(server.endpoint_url)
    this.transportType.set(server.transport_type)
    this.authType.set(server.auth_type)
    this.authSecret.set('')
    this.toolsInput.set(server.allowed_tools?.join(', ') || '')
    this.isAdding.set(true)
  }

  protected async handleSubmit(): Promise<void> {
    const name = this.name()
    const endpointUrl = this.endpointUrl()
    if (!name.trim() || !endpointUrl.trim()) return

    const allowedTools = this.toolsInput()
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)

    const payload: McpServerPayload = {
      name: name.trim(),
      description: this.description().trim() || undefined,
      endpoint_url: endpointUrl.trim(),
      transport_type: this.transportType(),
      auth_type: this.authType(),
      auth_secret: this.authSecret().trim() || undefined,
      allowed_tools: allowedTools,
    }

    this.busy.set(true)
    try {
      const editingId = this.editingId()
      if (editingId) {
        await this.onUpdateServer()(editingId, payload)
      } else {
        await this.onAddServer()(payload)
      }
      this.resetForm()
    } finally {
      this.busy.set(false)
    }
  }

  protected async handleToggleStatus(server: McpServerInfo): Promise<void> {
    const nextStatus = server.status === 'disabled' ? 'configured' : 'disabled'
    this.busy.set(true)
    try {
      await this.onUpdateServer()(server.id, { status: nextStatus })
    } finally {
      this.busy.set(false)
    }
  }

  protected async handleDelete(id: string, serverName: string): Promise<void> {
    if (!window.confirm(`¿Seguro que deseas eliminar el servidor MCP "${serverName}"?`)) return
    this.busy.set(true)
    try {
      await this.onDeleteServer()(id)
    } finally {
      this.busy.set(false)
    }
  }
}

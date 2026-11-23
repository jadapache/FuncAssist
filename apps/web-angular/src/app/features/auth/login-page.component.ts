import { ChangeDetectionStrategy, Component, OnInit, computed, effect, inject, signal } from '@angular/core'
import { Router } from '@angular/router'
import { AlertCircle, BadgeCheck, CheckCircle2, Circle, Eye, EyeOff, Lock, LogIn, Mail, Sparkles, User, UserPlus } from 'lucide'
import { EMAIL_REGEX, USERNAME_REGEX, roleOptions, type SelectableRole } from '../../constants/auth'
import { API_BASE } from '../../core/api/config'
import { AuthService } from '../../core/auth/auth.service'
import { ToastService } from '../../core/notifications/toast.service'
import { LucideIconDirective } from '../../shared/icons/lucide.directive'

interface PasswordRule {
  id: string
  label: string
  isValid: boolean
}

const evaluatePasswordRules = (pwd: string): PasswordRule[] => [
  { id: 'length', label: 'Mínimo 10 caracteres', isValid: pwd.length >= 10 },
  { id: 'uppercase', label: 'Al menos una letra mayúscula', isValid: /[A-Z]/.test(pwd) },
  { id: 'number', label: 'Al menos un número', isValid: /\d/.test(pwd) },
  { id: 'special', label: 'Al menos un carácter especial (!@#$%...)', isValid: /[^A-Za-z0-9]/.test(pwd) },
]

const INPUT_CLASS =
  'w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-10 pr-3 text-xs font-medium text-slate-800 placeholder-slate-400 focus:border-[#002777] focus:outline-none focus:ring-2 focus:ring-[#002777]/20 transition-all shadow-sm'

/** Login / access-request page (port of React `LoginPage`). */
@Component({
  selector: 'app-login-page',
  imports: [LucideIconDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display: contents' },
  template: `
    <div
      class="relative flex min-h-screen w-full flex-col items-center justify-center overflow-hidden bg-[linear-gradient(to_top_right,#8B0C3F_0%,#303E6D_100%)] p-4 sm:p-6 lg:p-8"
    >
      <!-- Subtle Grid Overlay -->
      <div
        class="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,#ffffff0a_1px,transparent_1px),linear-gradient(to_bottom,#ffffff0a_1px,transparent_1px)] bg-[size:4rem_4rem]"
      ></div>

      <!-- Main Card -->
      <div
        class="relative z-10 w-full max-w-md overflow-hidden rounded-3xl border border-slate-200/80 bg-white p-6 sm:p-8 shadow-2xl shadow-slate-950/20 backdrop-blur-xl"
      >
        <!-- Brand Header -->
        <div class="mb-6 flex flex-col items-center text-center">
          <div
            class="relative flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-[#002777] to-[#004497] text-white shadow-lg shadow-[#002777]/30 mb-2.5 transition-transform hover:scale-105"
          >
            <svg [lucide]="icons.Sparkles" class="h-6 w-6"></svg>
            <span
              class="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-cyan-400 ring-2 ring-white animate-pulse-soft"
              aria-hidden="true"
            ></span>
          </div>
          <div class="flex items-center justify-center gap-2">
            <span class="text-2xl font-bold tracking-tight text-[var(--color-ink)]">
              Func<span class="font-normal text-[var(--color-primary-accent)]">Assist</span>
            </span>
            @if (appVersion()) {
              <span
                class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600 border border-slate-200"
              >
                v{{ appVersion() }}
              </span>
            }
          </div>
          <h1 class="text-lg font-bold tracking-tight text-slate-800 mt-2">
            {{ mode() === 'login' ? 'Iniciar Sesión' : 'Solicitud de Acceso' }}
          </h1>
          <p class="text-xs text-slate-500 mt-0.5">
            {{
              mode() === 'login'
                ? 'Ingresa tus credenciales para acceder a la plataforma'
                : 'Completa tus datos para solicitar acceso a la plataforma'
            }}
          </p>
        </div>

        <!-- Tab Switcher -->
        <div class="mb-6 grid grid-cols-2 gap-2 rounded-2xl bg-slate-100 p-1.5 border border-slate-200">
          <button type="button" (click)="switchTab('login')" [class]="tabClass('login')">
            <svg [lucide]="icons.LogIn" class="h-3.5 w-3.5"></svg>
            Iniciar Sesión
          </button>
          <button type="button" (click)="switchTab('register')" [class]="tabClass('register')">
            <svg [lucide]="icons.UserPlus" class="h-3.5 w-3.5"></svg>
            Solicitar Acceso
          </button>
        </div>

        @if (successMsg()) {
          <div
            class="mb-5 flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-800 shadow-sm animate-in fade-in"
          >
            <svg [lucide]="icons.CheckCircle2" class="h-4 w-4 shrink-0 text-emerald-600 mt-0.5"></svg>
            <span class="leading-relaxed font-semibold">{{ successMsg() }}</span>
          </div>
        }

        @if (errorMsg()) {
          <div
            class="mb-5 flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-3.5 text-xs text-red-700 shadow-sm animate-in fade-in"
          >
            <svg [lucide]="icons.AlertCircle" class="h-4 w-4 shrink-0 text-red-600 mt-0.5"></svg>
            <span class="leading-relaxed font-medium">{{ errorMsg() }}</span>
          </div>
        }

        <form (submit)="handleSubmit($event)" class="space-y-4">
          <!-- Username -->
          <div>
            <div class="flex items-center justify-between mb-1.5">
              <label class="text-xs font-semibold text-slate-800">
                Nombre de Usuario <span class="text-red-500">*</span>
              </label>
              <div class="flex items-center gap-2">
                @if (mode() === 'register' && username().length > 0 && !isUsernameValid()) {
                  <span class="text-[10px] text-amber-600 font-medium">Solo letras y números</span>
                }
                <span class="text-[10px] text-slate-400 font-mono">{{ username().length }}/20</span>
              </div>
            </div>
            <div class="relative">
              <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
                <svg [lucide]="icons.User" class="h-4 w-4"></svg>
              </div>
              <input
                type="text"
                required
                maxlength="20"
                [value]="username()"
                (keydown)="onUsernameKeyDown($event)"
                (input)="username.set($any($event.target).value)"
                placeholder="ej. pepitoperez"
                [class]="inputClass"
              />
            </div>
          </div>

          @if (mode() === 'register') {
            <div>
              <div class="flex items-center justify-between mb-1.5">
                <label class="text-xs font-semibold text-slate-800">
                  Nombre Completo <span class="text-red-500">*</span>
                </label>
                <span class="text-[10px] text-slate-400 font-mono">{{ fullName().length }}/80</span>
              </div>
              <div class="relative">
                <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
                  <svg [lucide]="icons.BadgeCheck" class="h-4 w-4"></svg>
                </div>
                <input
                  type="text"
                  required
                  maxlength="80"
                  [value]="fullName()"
                  (input)="fullName.set($any($event.target).value)"
                  placeholder="ej. Pepito Perez"
                  [class]="inputClass"
                />
              </div>
            </div>

            <div>
              <div class="flex items-center justify-between mb-1.5">
                <label class="text-xs font-semibold text-slate-800">
                  Correo Electrónico <span class="text-red-500">*</span>
                </label>
                @if (email().length > 0 && !emailRegex.test(email())) {
                  <span class="text-[10px] text-amber-600 font-medium">Formato inválido</span>
                }
              </div>
              <div class="relative">
                <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
                  <svg [lucide]="icons.Mail" class="h-4 w-4"></svg>
                </div>
                <input
                  type="email"
                  required
                  [value]="email()"
                  (input)="email.set($any($event.target).value)"
                  placeholder="usuario@dominio.com"
                  [class]="inputClass"
                />
              </div>
            </div>

            <div>
              <label class="block text-xs font-semibold text-slate-800 mb-1.5">
                Rol Solicitado <span class="text-red-500">*</span>
              </label>
              <select
                [value]="role()"
                (change)="role.set($any($event.target).value)"
                class="w-full rounded-xl border border-slate-300 bg-white py-2.5 px-3 text-xs font-medium text-slate-800 focus:border-[#002777] focus:outline-none focus:ring-2 focus:ring-[#002777]/20 transition-all shadow-sm"
              >
                @for (opt of roleOptions; track opt.value) {
                  <option [value]="opt.value" [selected]="opt.value === role()">{{ opt.label }}</option>
                }
              </select>
              @if (selectedRoleInfo(); as info) {
                <p class="text-[11px] text-slate-500 mt-1 leading-normal">{{ info.description }}</p>
              }
            </div>
          }

          <!-- Password -->
          <div>
            <label class="block text-xs font-semibold text-slate-800 mb-1.5">
              Contraseña <span class="text-red-500">*</span>
            </label>
            <div class="relative">
              <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
                <svg [lucide]="icons.Lock" class="h-4 w-4"></svg>
              </div>
              <input
                [type]="showPassword() ? 'text' : 'password'"
                required
                [value]="password()"
                (input)="password.set($any($event.target).value)"
                placeholder="••••••••"
                class="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-10 pr-10 text-xs font-medium text-slate-800 placeholder-slate-400 focus:border-[#002777] focus:outline-none focus:ring-2 focus:ring-[#002777]/20 transition-all shadow-sm"
              />
              <button
                type="button"
                (click)="showPassword.set(!showPassword())"
                class="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
              >
                @if (showPassword()) {
                  <svg [lucide]="icons.EyeOff" class="h-4 w-4"></svg>
                } @else {
                  <svg [lucide]="icons.Eye" class="h-4 w-4"></svg>
                }
              </button>
            </div>
            @if (mode() === 'register') {
              <div class="mt-2.5 rounded-xl border border-slate-200/90 bg-slate-50/80 p-3">
                <p class="text-[11px] font-semibold text-slate-700 mb-2">Requisitos de la contraseña:</p>
                <ul class="space-y-1.5">
                  @for (rule of passwordRules(); track rule.id) {
                    <li class="flex items-center gap-2 text-[11px]">
                      @if (rule.isValid) {
                        <svg [lucide]="icons.CheckCircle2" class="h-3.5 w-3.5 text-emerald-600 shrink-0"></svg>
                      } @else {
                        <svg [lucide]="icons.Circle" class="h-3.5 w-3.5 text-slate-400 shrink-0"></svg>
                      }
                      <span [class]="rule.isValid ? 'text-emerald-700 font-medium' : 'text-slate-500'">{{
                        rule.label
                      }}</span>
                    </li>
                  }
                </ul>
              </div>
            }
          </div>

          <button
            type="submit"
            [disabled]="isSubmitDisabled()"
            class="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[#002777] to-[#004497] hover:from-[#001f5c] hover:to-[#00367a] py-3 text-xs font-bold text-white shadow-md focus:outline-none focus:ring-2 focus:ring-[#002777]/30 disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none transition-all cursor-pointer active:scale-[0.99]"
          >
            @if (isLoading()) {
              <div class="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></div>
            } @else if (mode() === 'login') {
              <svg [lucide]="icons.LogIn" class="h-4 w-4"></svg>
              Ingresar a la Plataforma
            } @else {
              <svg [lucide]="icons.UserPlus" class="h-4 w-4"></svg>
              Enviar Solicitud de Acceso
            }
          </button>
        </form>
      </div>
    </div>
  `,
})
export class LoginPageComponent implements OnInit {
  private readonly router = inject(Router)
  private readonly auth = inject(AuthService)
  private readonly toastService = inject(ToastService)

  protected readonly icons = {
    AlertCircle,
    BadgeCheck,
    CheckCircle2,
    Circle,
    Eye,
    EyeOff,
    Lock,
    LogIn,
    Mail,
    Sparkles,
    User,
    UserPlus,
  }
  protected readonly roleOptions = roleOptions
  protected readonly emailRegex = EMAIL_REGEX
  protected readonly inputClass = INPUT_CLASS

  protected readonly appVersion = signal<string | null>(null)
  protected readonly mode = signal<'login' | 'register'>('login')
  protected readonly username = signal('')
  protected readonly password = signal('')
  protected readonly fullName = signal('')
  protected readonly email = signal('')
  protected readonly role = signal<SelectableRole>('funcional')
  protected readonly showPassword = signal(false)
  protected readonly isLoading = signal(false)
  protected readonly errorMsg = signal<string | null>(null)
  protected readonly successMsg = signal<string | null>(null)

  protected readonly passwordRules = computed(() => evaluatePasswordRules(this.password()))
  private readonly allPasswordRulesMet = computed(() => this.passwordRules().every((r) => r.isValid))
  protected readonly isUsernameValid = computed(() => USERNAME_REGEX.test(this.username().trim()))
  protected readonly selectedRoleInfo = computed(() => roleOptions.find((r) => r.value === this.role()))

  protected readonly isSubmitDisabled = computed(() => {
    const isLoginFormComplete = Boolean(this.username().trim() && this.password())
    const isRegisterFormComplete = Boolean(
      this.username().trim() &&
        this.isUsernameValid() &&
        this.fullName().trim() &&
        this.email().trim() &&
        EMAIL_REGEX.test(this.email().trim()) &&
        this.role() &&
        this.allPasswordRulesMet(),
    )
    return this.isLoading() || (this.mode() === 'login' ? !isLoginFormComplete : !isRegisterFormComplete)
  })

  constructor() {
    // Redirect if already authenticated
    effect(() => {
      if (this.auth.isAuthenticated()) {
        void this.router.navigateByUrl('/', { replaceUrl: true })
      }
    })
  }

  ngOnInit(): void {
    fetch(`${API_BASE}/api/health`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { version?: string } | null) => {
        if (data?.version) this.appVersion.set(data.version)
      })
      .catch(() => {
        // Keep null if healthcheck is unreachable
      })
  }

  protected tabClass(tab: 'login' | 'register'): string {
    return `flex items-center justify-center gap-2 rounded-xl py-2.5 text-xs font-semibold transition-all cursor-pointer ${
      this.mode() === tab ? 'bg-[#002777] text-white shadow-md' : 'text-slate-600 hover:text-slate-900 hover:bg-white/60'
    }`
  }

  protected switchTab(newMode: 'login' | 'register'): void {
    this.mode.set(newMode)
    this.errorMsg.set(null)
    this.successMsg.set(null)
  }

  protected onUsernameKeyDown(e: KeyboardEvent): void {
    if (this.mode() === 'register' && e.key === ' ') e.preventDefault()
  }

  protected async handleSubmit(e: Event): Promise<void> {
    e.preventDefault()
    this.errorMsg.set(null)
    this.successMsg.set(null)

    const trimmedUsername = this.username().trim()
    const trimmedFullName = this.fullName().trim()
    const trimmedEmail = this.email().trim()

    if (!trimmedUsername) return this.fail('El nombre de usuario es requerido.')

    if (this.mode() === 'login') {
      if (!this.password()) return this.fail('La contraseña es requerida.')
    } else {
      if (trimmedUsername.length < 3 || trimmedUsername.length > 20)
        return this.fail('El nombre de usuario debe tener entre 3 y 20 caracteres.')
      if (!USERNAME_REGEX.test(trimmedUsername)) return this.fail('El nombre de usuario admite solo letras y números.')
      if (!trimmedFullName) return this.fail('El nombre completo es requerido.')
      if (trimmedFullName.length > 80) return this.fail('El nombre completo no debe superar los 80 caracteres.')
      if (!trimmedEmail) return this.fail('El correo electrónico es requerido.')
      if (!EMAIL_REGEX.test(trimmedEmail))
        return this.fail('Por favor ingresa un correo electrónico válido (ej. usuario@dominio.com).')
      if (!this.allPasswordRulesMet())
        return this.fail(
          'La contraseña debe tener al menos 10 caracteres, incluir al menos una letra mayúscula, un número y un carácter especial.',
        )
    }

    this.isLoading.set(true)
    try {
      if (this.mode() === 'login') {
        await this.auth.login(trimmedUsername, this.password())
        this.toastService.toast.success(`¡Bienvenido de nuevo, ${trimmedUsername}!`, 'Sesión iniciada')
        void this.router.navigateByUrl('/', { replaceUrl: true })
      } else {
        const res = await this.auth.register(trimmedUsername, this.password(), trimmedEmail, trimmedFullName, this.role())
        if (res.status === 'approved' && res.token) {
          this.toastService.toast.success('¡Cuenta de Administrador creada y aprobada!', 'Bienvenido')
          void this.router.navigateByUrl('/', { replaceUrl: true })
        } else {
          this.successMsg.set(
            res.message ||
              'Solicitud de acceso enviada correctamente. Un administrador debe aprobar tu cuenta antes de que puedas ingresar.',
          )
          this.password.set('')
        }
      }
    } catch (err: unknown) {
      this.errorMsg.set(err instanceof Error ? err.message : 'Error al procesar la solicitud')
    } finally {
      this.isLoading.set(false)
    }
  }

  private fail(message: string): void {
    this.errorMsg.set(message)
  }
}

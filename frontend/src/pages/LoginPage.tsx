import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  BadgeCheck,
  CheckCircle2,
  Eye,
  EyeOff,
  Lock,
  LogIn,
  Mail,
  Sparkles,
  User,
  UserPlus,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import {
  EMAIL_REGEX,
  PASSWORD_REGEX,
  USERNAME_REGEX,
  roleOptions,
  type SelectableRole,
} from '../constants/auth'

export const LoginPage: React.FC = () => {
  const navigate = useNavigate()
  const { login, register, isAuthenticated } = useAuth()
  const { toast } = useToast()

  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<SelectableRole>('funcional')

  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const isPasswordRobust = PASSWORD_REGEX.test(password)
  const isUsernameValid = USERNAME_REGEX.test(username.trim())

  // Enable/disable conditions based on completion of fields
  const isLoginFormComplete = Boolean(username.trim() && password)
  const isRegisterFormComplete = Boolean(
    username.trim() &&
    isUsernameValid &&
    fullName.trim() &&
    email.trim() &&
    EMAIL_REGEX.test(email.trim()) &&
    role &&
    password &&
    isPasswordRobust
  )
  const isSubmitDisabled =
    isLoading || (mode === 'login' ? !isLoginFormComplete : !isRegisterFormComplete)

  // Redirect if already authenticated
  React.useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true })
    }
  }, [isAuthenticated, navigate])

  const switchTab = (newMode: 'login' | 'register') => {
    setMode(newMode)
    setErrorMsg(null)
    setSuccessMsg(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMsg(null)
    setSuccessMsg(null)

    const trimmedUsername = username.trim()
    const trimmedFullName = fullName.trim()
    const trimmedEmail = email.trim()

    // Required fields validation
    if (!trimmedUsername) {
      setErrorMsg('El nombre de usuario es requerido.')
      return
    }

    if (mode === 'login') {
      if (!password) {
        setErrorMsg('La contraseña es requerida.')
        return
      }
    } else {
      // Register validation
      if (trimmedUsername.length < 3 || trimmedUsername.length > 20) {
        setErrorMsg('El nombre de usuario debe tener entre 3 y 20 caracteres.')
        return
      }

      if (!USERNAME_REGEX.test(trimmedUsername)) {
        setErrorMsg('El nombre de usuario admite solo letras y números.')
        return
      }

      if (!trimmedFullName) {
        setErrorMsg('El nombre completo es requerido.')
        return
      }

      if (trimmedFullName.length > 80) {
        setErrorMsg('El nombre completo no debe superar los 80 caracteres.')
        return
      }

      if (!trimmedEmail) {
        setErrorMsg('El correo electrónico es requerido.')
        return
      }

      if (!EMAIL_REGEX.test(trimmedEmail)) {
        setErrorMsg('Por favor ingresa un correo electrónico válido (ej. usuario@dominio.com).')
        return
      }

      if (!isPasswordRobust) {
        setErrorMsg(
          'La contraseña debe tener al menos 10 caracteres, incluir al menos una letra mayúscula, un número y un carácter especial.',
        )
        return
      }
    }

    setIsLoading(true)

    try {
      if (mode === 'login') {
        await login(trimmedUsername, password)
        toast.success(`¡Bienvenido de nuevo, ${trimmedUsername}!`, 'Sesión iniciada')
        navigate('/', { replace: true })
      } else {
        const res = await register(
          trimmedUsername,
          password,
          trimmedEmail,
          trimmedFullName,
          role,
        )
        if (res.status === 'approved' && res.token) {
          toast.success('¡Cuenta de Administrador creada y aprobada!', 'Bienvenido')
          navigate('/', { replace: true })
        } else {
          setSuccessMsg(
            res.message ||
            'Solicitud de acceso enviada correctamente. Un administrador debe aprobar tu cuenta antes de que puedas ingresar.',
          )
          setPassword('')
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al procesar la solicitud'
      setErrorMsg(msg)
    } finally {
      setIsLoading(false)
    }
  }

  const selectedRoleInfo = roleOptions.find((r) => r.value === role)

  return (
    <div className="relative flex min-h-screen w-full flex-col items-center justify-center overflow-hidden bg-[linear-gradient(to_top_right,#8B0C3F_0%,#303E6D_100%)] p-4 sm:p-6 lg:p-8">
      {/* Subtle Grid Overlay */}
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,#ffffff0a_1px,transparent_1px),linear-gradient(to_bottom,#ffffff0a_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      {/* Main Card */}
      <div className="relative z-10 w-full max-w-md overflow-hidden rounded-3xl border border-slate-200/80 bg-white p-6 sm:p-8 shadow-2xl shadow-slate-950/20 backdrop-blur-xl">
        {/* Brand Header */}
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="relative flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-[#002777] to-[#004497] text-white shadow-lg shadow-[#002777]/30 mb-2.5 transition-transform hover:scale-105">
            <Sparkles className="h-6 w-6" aria-hidden />
            <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-cyan-400 ring-2 ring-white animate-pulse-soft" aria-hidden />
          </div>
          <div className="text-2xl font-bold tracking-tight text-[var(--color-ink)]">
            Func<span className="font-normal text-[var(--color-primary-accent)]">Assist</span>
          </div>
          <h1 className="text-lg font-bold tracking-tight text-slate-800 mt-2">
            {mode === 'login' ? 'Iniciar Sesión' : 'Solicitud de Acceso'}
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            {mode === 'login'
              ? 'Ingresa tus credenciales para acceder a la plataforma'
              : 'Completa tus datos para solicitar acceso a la plataforma'}
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="mb-6 grid grid-cols-2 gap-2 rounded-2xl bg-slate-100 p-1.5 border border-slate-200">
          <button
            type="button"
            onClick={() => switchTab('login')}
            className={`flex items-center justify-center gap-2 rounded-xl py-2.5 text-xs font-semibold transition-all cursor-pointer ${mode === 'login'
              ? 'bg-[#002777] text-white shadow-md'
              : 'text-slate-600 hover:text-slate-900 hover:bg-white/60'
              }`}
          >
            <LogIn className="h-3.5 w-3.5" />
            Iniciar Sesión
          </button>
          <button
            type="button"
            onClick={() => switchTab('register')}
            className={`flex items-center justify-center gap-2 rounded-xl py-2.5 text-xs font-semibold transition-all cursor-pointer ${mode === 'register'
              ? 'bg-[#002777] text-white shadow-md'
              : 'text-slate-600 hover:text-slate-900 hover:bg-white/60'
              }`}
          >
            <UserPlus className="h-3.5 w-3.5" />
            Solicitar Acceso
          </button>
        </div>

        {/* Success Alert Banner */}
        {successMsg && (
          <div className="mb-5 flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-800 shadow-sm animate-in fade-in">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 mt-0.5" />
            <span className="leading-relaxed font-semibold">{successMsg}</span>
          </div>
        )}

        {/* Error Alert Banner */}
        {errorMsg && (
          <div className="mb-5 flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-3.5 text-xs text-red-700 shadow-sm animate-in fade-in">
            <AlertCircle className="h-4 w-4 shrink-0 text-red-600 mt-0.5" />
            <span className="leading-relaxed font-medium">{errorMsg}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Username */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-semibold text-slate-800">
                Nombre de Usuario <span className="text-red-500">*</span>
              </label>
              <div className="flex items-center gap-2">
                {mode === 'register' && username.length > 0 && !isUsernameValid && (
                  <span className="text-[10px] text-amber-600 font-medium">Solo letras y números</span>
                )}
                <span className="text-[10px] text-slate-400 font-mono">
                  {username.length}/20
                </span>
              </div>
            </div>
            <div className="relative">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
                <User className="h-4 w-4" />
              </div>
              <input
                type="text"
                required
                maxLength={20}
                value={username}
                onKeyDown={(e) => {
                  if (mode === 'register' && e.key === ' ') {
                    e.preventDefault()
                  }
                }}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="ej. pepitoperez"
                className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-10 pr-3 text-xs font-medium text-slate-800 placeholder-slate-400 focus:border-[#002777] focus:outline-none focus:ring-2 focus:ring-[#002777]/20 transition-all shadow-sm"
              />
            </div>
          </div>

          {/* Registration specific fields */}
          {mode === 'register' && (
            <>
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-semibold text-slate-800">
                    Nombre Completo <span className="text-red-500">*</span>
                  </label>
                  <span className="text-[10px] text-slate-400 font-mono">
                    {fullName.length}/80
                  </span>
                </div>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
                    <BadgeCheck className="h-4 w-4" />
                  </div>
                  <input
                    type="text"
                    required
                    maxLength={80}
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="ej. Pepito Perez"
                    className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-10 pr-3 text-xs font-medium text-slate-800 placeholder-slate-400 focus:border-[#002777] focus:outline-none focus:ring-2 focus:ring-[#002777]/20 transition-all shadow-sm"
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-semibold text-slate-800">
                    Correo Electrónico <span className="text-red-500">*</span>
                  </label>
                  {email.length > 0 && !EMAIL_REGEX.test(email) && (
                    <span className="text-[10px] text-amber-600 font-medium">Formato inválido</span>
                  )}
                </div>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
                    <Mail className="h-4 w-4" />
                  </div>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="usuario@dominio.com"
                    className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-10 pr-3 text-xs font-medium text-slate-800 placeholder-slate-400 focus:border-[#002777] focus:outline-none focus:ring-2 focus:ring-[#002777]/20 transition-all shadow-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-800 mb-1.5">
                  Rol Solicitado <span className="text-red-500">*</span>
                </label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as SelectableRole)}
                  className="w-full rounded-xl border border-slate-300 bg-white py-2.5 px-3 text-xs font-medium text-slate-800 focus:border-[#002777] focus:outline-none focus:ring-2 focus:ring-[#002777]/20 transition-all shadow-sm"
                >
                  {roleOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                {selectedRoleInfo && (
                  <p className="text-[11px] text-slate-500 mt-1 leading-normal">
                    {selectedRoleInfo.description}
                  </p>
                )}
              </div>
            </>
          )}

          {/* Password */}
          <div>
            <label className="block text-xs font-semibold text-slate-800 mb-1.5">
              Contraseña <span className="text-red-500">*</span>
            </label>
            <div className="relative">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
                <Lock className="h-4 w-4" />
              </div>
              <input
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-10 pr-10 text-xs font-medium text-slate-800 placeholder-slate-400 focus:border-[#002777] focus:outline-none focus:ring-2 focus:ring-[#002777]/20 transition-all shadow-sm"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isSubmitDisabled}
            className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[#002777] to-[#004497] hover:from-[#001f5c] hover:to-[#00367a] py-3 text-xs font-bold text-white shadow-md focus:outline-none focus:ring-2 focus:ring-[#002777]/30 disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none transition-all cursor-pointer active:scale-[0.99]"
          >
            {isLoading ? (
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : mode === 'login' ? (
              <>
                <LogIn className="h-4 w-4" />
                Ingresar a la Plataforma
              </>
            ) : (
              <>
                <UserPlus className="h-4 w-4" />
                Enviar Solicitud de Acceso
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}

import { useState, type FormEvent } from 'react'
import { useUser, type UserRole } from '../../../context/UserContext'
import { useToast } from '../../../context/ToastContext'

const roleOptions: { value: UserRole; label: string; description: string }[] = [
  {
    value: 'funcional',
    label: 'Analista Funcional',
    description: 'Generación de mejoras funcionales, procesamiento de transcripciones y requerimientos',
  },
  {
    value: 'pm',
    label: 'Director de Proyecto',
    description: 'Gestión de proyectos, standups diarios, revisión de PRDs e impacto',
  },
  {
    value: 'qa',
    label: 'Tester',
    description: 'Pruebas de integración, pruebas de regresión, planes de testeo, casos de prueba, etc.',
  },
]

export const FirstTimeSetup = () => {
  const { completeSetup } = useUser()
  const { toast } = useToast()
  const [displayName, setDisplayName] = useState('')
  const [selectedRole, setSelectedRole] = useState<UserRole>('funcional')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!displayName.trim()) {
      toast.warning('Por favor ingresa tu nombre')
      return
    }

    setIsSubmitting(true)
    try {
      await completeSetup({
        display_name: displayName.trim(),
        user_role: selectedRole,
      })
      toast.success('¡Perfil configurado exitosamente!')
    } catch (error) {
      console.error('Error completando setup:', error)
      toast.error('Error al configurar el perfil. Inténtalo de nuevo.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="relative flex min-h-screen w-full flex-col items-center justify-center overflow-hidden bg-[linear-gradient(to_top_right,#8B0C3F_0%,#303E6D_100%)] p-4 sm:p-6 lg:p-8">
      {/* Subtle Grid Overlay */}
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,#ffffff0a_1px,transparent_1px),linear-gradient(to_bottom,#ffffff0a_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      {/* Main Card: Solid White */}
      <div className="relative z-10 w-full max-w-md overflow-hidden rounded-3xl border border-slate-200/80 bg-white p-6 sm:p-8 shadow-2xl shadow-slate-950/20 backdrop-blur-xl transition-all">
        {/* Header */}
        <div className="text-center mb-5">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-blue-100 text-[#002777] mb-2 shadow-sm">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
              />
            </svg>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
            Bienvenido a QA Project MGMT
          </h1>
          <p className="text-slate-500 text-xs sm:text-sm mt-1">
            Configura tu perfil inicial para personalizar las herramientas disponibles
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Display Name Input */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              ¿Cómo te llamas? *
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Ej: Pepito Pérez"
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 outline-none transition text-slate-900 font-medium text-sm"
              required
              autoFocus
            />
          </div>

          {/* Role Selection with Radio Buttons (Single-line description) */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Selecciona tu rol de trabajo *
            </label>
            <div className="space-y-2">
              {roleOptions.map((option) => {
                const isSelected = selectedRole === option.value
                return (
                  <label
                    key={option.value}
                    className={`
                      flex items-center gap-3 px-3.5 py-2.5 rounded-xl border-2 cursor-pointer transition-all duration-150
                      ${isSelected
                        ? 'border-blue-600 bg-blue-50/70 shadow-sm'
                        : 'border-slate-200 hover:border-slate-300 bg-white'
                      }
                    `}
                  >
                    <input
                      type="radio"
                      name="role"
                      value={option.value}
                      checked={isSelected}
                      onChange={(e) => setSelectedRole(e.target.value as UserRole)}
                      className="sr-only"
                    />
                    <div
                      className={`
                        w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 transition
                        ${isSelected ? 'border-blue-600 bg-blue-600' : 'border-slate-300 bg-white'}
                      `}
                    >
                      {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold text-slate-900 text-xs sm:text-sm leading-tight">
                        {option.label}
                      </div>
                      <p
                        className="text-[11px] text-slate-500 truncate leading-tight mt-0.5"
                        title={option.description}
                      >
                        {option.description}
                      </p>
                    </div>
                  </label>
                )
              })}
            </div>
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={!displayName.trim() || isSubmitting}
              className="w-full py-3 px-5 rounded-xl bg-gradient-to-r from-[#002777] to-[#004497] text-white font-bold hover:opacity-95 disabled:opacity-50 disabled:cursor-not-allowed transition shadow-md shadow-[#002777]/20 text-sm cursor-pointer"
            >
              {isSubmitting ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Configurando...
                </span>
              ) : (
                'Comenzar'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

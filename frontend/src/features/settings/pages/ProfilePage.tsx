import type { FormEvent } from 'react'
import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Pencil,
  Shield,
  Sparkles,
  X,
} from 'lucide-react'
import { api } from '../../../api/client'
import { PageHeader } from '../../../components/common'
import { useUser, type UserRole } from '../../../context/UserContext'
import { useToast } from '../../../context/ToastContext'

type OutletContext = {
  displayName: string
  setDisplayName: (name: string) => void
}

const roleLabels: Record<UserRole, string> = {
  admin: 'Administrador',
  pm: 'Project Manager',
  funcional: 'Analista Funcional',
  qa: 'Tester',
}

export const ProfilePage = () => {
  const { displayName, setDisplayName } = useOutletContext<OutletContext>()
  const { user, updateProfile } = useUser()
  const { toast } = useToast()

  // Inline editing state for name
  const [isEditingName, setIsEditingName] = useState(false)
  const [nameInput, setNameInput] = useState(user?.display_name || displayName || 'Usuario')
  const [savingName, setSavingName] = useState(false)

  // Standup Rubric State
  const [standupRubric, setStandupRubric] = useState('')
  const [savingRubric, setSavingRubric] = useState(false)

  // Status & Feedback
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const activeName = user?.display_name || nameInput
  const activeRole: UserRole = user?.user_role || 'admin'
  const activeRoleLabel = roleLabels[activeRole] || 'Usuario'
  const isPmUser = activeRole === 'pm' || activeRole === 'admin'

  const getInitials = (nameStr: string) => {
    const parts = nameStr.trim().split(/\s+/).filter(Boolean)
    if (parts.length === 0) return 'U'
    if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase()
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
  }

  const initials = getInitials(activeName)

  useEffect(() => {
    if (user?.display_name) {
      setNameInput(user.display_name)
    }
  }, [user])

  useEffect(() => {
    if (!isPmUser) return
    const load = async () => {
      try {
        const rubric = await api.getRubric('standup')
        setStandupRubric(((rubric.criteria as string[]) || []).join('\n'))
      } catch {
        // ignore on boot
      }
    }
    void load()
  }, [isPmUser])

  const handleSaveName = async () => {
    if (!nameInput.trim()) {
      toast.warning('El nombre es obligatorio.')
      return
    }

    setSavingName(true)
    setError(null)
    setMessage(null)

    try {
      await updateProfile({
        display_name: nameInput.trim(),
      })
      setDisplayName(nameInput.trim())
      setIsEditingName(false)
      const successMsg = 'Nombre de usuario actualizado exitosamente.'
      setMessage(successMsg)
      toast.success(successMsg)
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Error al actualizar el nombre'
      setError(errMsg)
      toast.error(errMsg)
    } finally {
      setSavingName(false)
    }
  }

  const handleRubricSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setMessage(null)
    setSavingRubric(true)
    try {
      const criteria = standupRubric
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
      await api.updateRubric('standup', criteria)
      const successMsg = 'Rúbrica de evaluación Standup actualizada exitosamente.'
      setMessage(successMsg)
      toast.success(successMsg)
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Error al actualizar la rúbrica'
      setError(errMsg)
      toast.error(errMsg)
    } finally {
      setSavingRubric(false)
    }
  }

  return (
    <div className="space-y-8 pb-12">
      <PageHeader
        eyebrow="CUENTA & PERFIL"
        title="Perfil de Usuario"
        subtitle="Visualiza tu cuenta local y personaliza tu nombre de usuario."
      />

      {/* Global Alerts */}
      {message ? (
        <div className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-medium text-emerald-800">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" />
          <span>{message}</span>
        </div>
      ) : null}

      {error ? (
        <div className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-800">
          <AlertCircle className="h-5 w-5 shrink-0 text-red-600" />
          <span>{error}</span>
        </div>
      ) : null}

      {/* Profile Card */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 md:p-8 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center gap-5">
          <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#002777] to-[#004497] text-white font-extrabold text-2xl shadow-lg shadow-[#002777]/25 ring-4 ring-blue-100">
            {initials}
          </div>
          <div className="space-y-1.5 flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              {isEditingName ? (
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={nameInput}
                    onChange={(e) => setNameInput(e.target.value)}
                    placeholder="Tu nombre"
                    className="px-3 py-1.5 text-xl font-bold text-slate-900 border border-blue-400 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100 shadow-inner"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void handleSaveName()
                      if (e.key === 'Escape') {
                        setNameInput(user?.display_name || displayName || 'Usuario')
                        setIsEditingName(false)
                      }
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => void handleSaveName()}
                    disabled={savingName || !nameInput.trim()}
                    className="p-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 cursor-pointer shadow-sm transition"
                    title="Guardar nombre"
                    aria-label="Guardar nombre"
                  >
                    <Check className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setNameInput(user?.display_name || displayName || 'Usuario')
                      setIsEditingName(false)
                    }}
                    className="p-2 rounded-xl bg-slate-100 text-slate-600 hover:bg-slate-200 cursor-pointer transition"
                    title="Cancelar"
                    aria-label="Cancelar"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2.5">
                  <h2 className="text-2xl font-bold text-slate-900 truncate" title={activeName}>
                    {activeName}
                  </h2>
                  <button
                    type="button"
                    onClick={() => setIsEditingName(true)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-blue-700 hover:bg-blue-50 transition-colors cursor-pointer"
                    title="Editar nombre"
                    aria-label="Editar nombre"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                </div>
              )}

              <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 border border-blue-200 px-3 py-1 text-xs font-semibold text-[#002777]">
                <Shield className="h-3.5 w-3.5" /> {activeRoleLabel}
              </span>
            </div>

            <p className="text-sm text-slate-500">
              Perfil local almacenado en <code className="bg-slate-100 px-1.5 py-0.5 rounded text-slate-700 font-mono text-xs">app.json</code>
            </p>
          </div>
        </div>
      </div>

      {/* Standup Rubric Form - Only visible to PM / Admin role */}
      {isPmUser && (
        <div className="max-w-2xl">
          <form
            onSubmit={(e) => void handleRubricSubmit(e)}
            className="card space-y-5 border border-slate-200 bg-white p-6 md:p-8 shadow-sm rounded-2xl flex flex-col justify-between"
          >
            <div className="space-y-4">
              <div className="flex items-center gap-2.5 border-b border-slate-100 pb-4">
                <div className="p-1.5 rounded-lg bg-blue-100 text-blue-700">
                  <Sparkles className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900">Rúbrica de Evaluación Standup</h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Criterios utilizados para validar la completitud del resumen diario.
                  </p>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-800 block">
                  Criterios (uno por línea)
                </label>
                <textarea
                  value={standupRubric}
                  onChange={(e) => setStandupRubric(e.target.value)}
                  rows={7}
                  placeholder="Un criterio por línea..."
                  className="input-field font-mono text-xs leading-relaxed border border-slate-300 rounded-xl"
                />
                <p className="text-[11px] text-slate-400">
                  El agente de IA evaluará las respuestas del standup comparándolas contra estas pautas.
                </p>
              </div>
            </div>

            <div className="flex justify-end pt-4 border-t border-slate-100">
              <button
                type="submit"
                disabled={savingRubric}
                className="bg-blue-600 hover:bg-blue-700 text-white font-medium px-5 py-2.5 rounded-xl shadow-sm transition flex items-center gap-2 cursor-pointer text-sm"
              >
                <Check className="h-4 w-4" />
                <span>{savingRubric ? 'Guardando...' : 'Guardar Rúbrica'}</span>
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}

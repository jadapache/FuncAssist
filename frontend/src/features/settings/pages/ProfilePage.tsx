import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import {
  AlertCircle,
  Calendar,
  Check,
  CheckCircle2,
  FolderOpen,
  Key,
  Pencil,
  Shield,
  X,
} from 'lucide-react'
import { api } from '../../../api/client'
import { PageHeader } from '../../../components/common'
import { useAuth } from '../../../context/AuthContext'
import { useUser, type UserRole } from '../../../context/UserContext'
import { useToast } from '../../../context/ToastContext'
import { ChangePasswordModal } from '../components/ChangePasswordModal'

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

const formatDate = (isoStr?: string) => {
  if (!isoStr) return null
  try {
    const d = new Date(isoStr)
    if (isNaN(d.getTime())) return null
    return d.toLocaleDateString('es-ES', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
  } catch {
    return null
  }
}

export const ProfilePage = () => {
  const { displayName, setDisplayName } = useOutletContext<OutletContext>()
  const { user: authUser } = useAuth()
  const { user, updateProfile } = useUser()
  const { toast } = useToast()

  // Inline editing state for name
  const [isEditingName, setIsEditingName] = useState(false)
  const [nameInput, setNameInput] = useState(user?.display_name || displayName || 'Usuario')
  const [savingName, setSavingName] = useState(false)

  // Document Storage Path State
  const [docsPath, setDocsPath] = useState('')
  const [isEditingDocsPath, setIsEditingDocsPath] = useState(false)
  const [docsPathInput, setDocsPathInput] = useState('')
  const [savingDocsPath, setSavingDocsPath] = useState(false)

  // Password Change Modal State
  const [isPasswordModalOpen, setIsPasswordModalOpen] = useState(false)

  // Status & Feedback
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const activeName = user?.display_name || nameInput
  const activeRole: UserRole = user?.user_role || 'admin'
  const activeRoleLabel = roleLabels[activeRole] || 'Usuario'
  const memberSince = formatDate(authUser?.created_at)

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
    const loadProfile = async () => {
      try {
        const profile = await api.getUserProfile()
        if (profile.documents_path) {
          setDocsPath(profile.documents_path)
          setDocsPathInput(profile.documents_path)
        }
      } catch {
        // Fallback default
      }
    }
    void loadProfile()
  }, [])

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

  const handleSaveDocsPath = async () => {
    if (!docsPathInput.trim()) {
      toast.warning('La ruta de documentos no puede estar vacía.')
      return
    }

    setSavingDocsPath(true)
    setError(null)
    setMessage(null)

    try {
      const res = await api.updateUserProfile({
        documents_path: docsPathInput.trim(),
      })
      if (res.documents_path) {
        setDocsPath(res.documents_path)
        setDocsPathInput(res.documents_path)
      }
      setIsEditingDocsPath(false)
      const successMsg = 'Ruta de almacenamiento de documentos y transcripciones actualizada.'
      setMessage(successMsg)
      toast.success(successMsg)
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Error al actualizar la ruta'
      setError(errMsg)
      toast.error(errMsg)
    } finally {
      setSavingDocsPath(false)
    }
  }

  const handlePasswordSubmit = async (password: string) => {
    setError(null)
    setMessage(null)

    await api.updateProfile({
      password,
    })
    const successMsg = 'Contraseña actualizada exitosamente.'
    setMessage(successMsg)
    toast.success(successMsg)
  }

  return (
    <div className="space-y-8 pb-12">
      <PageHeader
        eyebrow="CUENTA & PERFIL"
        title="Perfil de Usuario"
        subtitle="Visualiza tu cuenta, preferencias de almacenamiento y seguridad."
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

              <button
                type="button"
                onClick={() => setIsPasswordModalOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold text-[#002777] bg-white border border-blue-200 hover:bg-blue-50 transition cursor-pointer shadow-2xs"
              >
                <Key className="h-3.5 w-3.5 text-[#002777]" />
                <span>Cambiar contraseña</span>
              </button>
            </div>

            <p className="text-sm text-slate-500 flex items-center gap-1.5">
              <Calendar className="h-3.5 w-3.5 text-slate-400" />
              <span>
                {memberSince ? `Se unió el ${memberSince}` : 'Cuenta de usuario'}
              </span>
            </p>
          </div>
        </div>
      </div>

      {/* Storage Path Card */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 md:p-8 shadow-sm">
        <div className="flex items-center gap-2.5 border-b border-slate-100 pb-4 mb-5">
          <div className="p-1.5 rounded-lg bg-blue-100 text-[#002777]">
            <FolderOpen className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">Ubicación de Documentos y Transcripciones</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Ruta en tu equipo donde se guardan los archivos TXT, JSON y documentos generados.
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <label className="text-xs font-semibold text-slate-800 block">
            Ruta en disco (Carpeta de Documentos)
          </label>
          {isEditingDocsPath ? (
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <input
                type="text"
                value={docsPathInput}
                onChange={(e) => setDocsPathInput(e.target.value)}
                placeholder="C:\Users\tu_usuario\Documents\FuncAssist"
                className="flex-1 px-3 py-2 text-sm font-mono text-slate-900 border border-blue-400 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100 shadow-inner"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void handleSaveDocsPath()
                  if (e.key === 'Escape') {
                    setDocsPathInput(docsPath)
                    setIsEditingDocsPath(false)
                  }
                }}
              />
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleSaveDocsPath()}
                  disabled={savingDocsPath || !docsPathInput.trim()}
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium disabled:opacity-50 cursor-pointer shadow-sm transition flex items-center gap-1.5"
                >
                  <Check className="h-4 w-4" />
                  <span>{savingDocsPath ? 'Guardando...' : 'Guardar'}</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDocsPathInput(docsPath)
                    setIsEditingDocsPath(false)
                  }}
                  className="px-3 py-2 rounded-xl bg-slate-100 text-slate-600 hover:bg-slate-200 text-sm font-medium cursor-pointer transition flex items-center gap-1"
                >
                  <X className="h-4 w-4" />
                  <span>Cancelar</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-slate-50 border border-slate-200 rounded-xl">
              <code className="text-xs font-mono text-slate-800 break-all select-all">
                {docsPath || 'Cargando ruta...'}
              </code>
              <button
                type="button"
                onClick={() => {
                  setDocsPathInput(docsPath)
                  setIsEditingDocsPath(true)
                }}
                className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-blue-700 bg-white border border-blue-200 hover:bg-blue-50 transition cursor-pointer shadow-2xs"
              >
                <Pencil className="h-3.5 w-3.5" />
                <span>Cambiar ruta</span>
              </button>
            </div>
          )}
          <p className="text-[11px] text-slate-400">
            Esta preferencia se sincroniza con tu cuenta y es la ruta destino para las transcripciones y documentos generados.
          </p>
        </div>
      </div>

      {/* Change Password Modal */}
      <ChangePasswordModal
        isOpen={isPasswordModalOpen}
        onClose={() => setIsPasswordModalOpen(false)}
        onSuccess={() => setIsPasswordModalOpen(false)}
        onSubmitPassword={handlePasswordSubmit}
      />
    </div>
  )
}

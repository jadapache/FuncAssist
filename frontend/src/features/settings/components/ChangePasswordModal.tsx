import React, { useState, type FormEvent } from 'react'
import { Key, Lock, Check, X, Loader2 } from 'lucide-react'

export interface ChangePasswordModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  onSubmitPassword: (password: string) => Promise<void>
}

export const ChangePasswordModal: React.FC<ChangePasswordModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  onSubmitPassword,
}) => {
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (!isOpen) return null

  const handleClose = () => {
    if (isSubmitting) return
    setNewPassword('')
    setConfirmPassword('')
    setError(null)
    onClose()
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)

    if (newPassword.length < 10) {
      setError('La nueva contraseña debe tener al menos 10 caracteres.')
      return
    }
    if (!/(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9])/.test(newPassword)) {
      setError('Debe contener al menos una mayúscula, un número y un símbolo especial.')
      return
    }
    if (newPassword !== confirmPassword) {
      setError('Las contraseñas no coinciden.')
      return
    }

    setIsSubmitting(true)
    try {
      await onSubmitPassword(newPassword)
      setNewPassword('')
      setConfirmPassword('')
      onSuccess()
      onClose()
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Error al actualizar la contraseña'
      setError(errMsg)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-labelledby="change-password-modal-title"
    >
      <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 animate-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-blue-50 text-[#002777]">
              <Key className="h-5 w-5" />
            </div>
            <div>
              <h3 id="change-password-modal-title" className="text-base font-bold text-slate-900">
                Cambiar Contraseña
              </h3>
              <p className="text-xs text-slate-500">
                Actualiza tu clave de acceso a la plataforma.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            disabled={isSubmitting}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition cursor-pointer disabled:opacity-50"
            aria-label="Cerrar modal"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {error ? (
          <div className="mt-4 p-3 rounded-xl border border-red-200 bg-red-50 text-xs font-medium text-red-800">
            {error}
          </div>
        ) : null}

        <form onSubmit={(e) => void handleSubmit(e)} className="mt-4 space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-800 block">
              Nueva contraseña
            </label>
            <div className="relative">
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Mínimo 10 caracteres"
                className="w-full pl-9 pr-3 py-2 text-sm text-slate-900 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
                required
                disabled={isSubmitting}
              />
              <Lock className="h-4 w-4 text-slate-400 absolute left-3 top-2.5" />
            </div>
            <p className="text-[11px] text-slate-400">
              Debe incluir al menos una mayúscula, un número y un símbolo especial.
            </p>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-800 block">
              Confirmar nueva contraseña
            </label>
            <div className="relative">
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Repite la nueva contraseña"
                className="w-full pl-9 pr-3 py-2 text-sm text-slate-900 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-100"
                required
                disabled={isSubmitting}
              />
              <Lock className="h-4 w-4 text-slate-400 absolute left-3 top-2.5" />
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
            <button
              type="button"
              onClick={handleClose}
              disabled={isSubmitting}
              className="px-3.5 py-2 rounded-xl bg-slate-100 text-slate-600 hover:bg-slate-200 text-xs font-medium cursor-pointer transition disabled:opacity-50"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !newPassword || !confirmPassword}
              className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium disabled:opacity-50 cursor-pointer shadow-sm transition flex items-center gap-1.5"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Actualizando...</span>
                </>
              ) : (
                <>
                  <Check className="h-3.5 w-3.5" />
                  <span>Actualizar contraseña</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}


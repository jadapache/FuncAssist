import { useCallback, useEffect, useState } from 'react'
import { api, type AuthUser } from '../../../api/client'
import { useToast } from '../../../context/ToastContext'

export function useUserApprovalsManager() {
  const { toast } = useToast()
  const [pendingRequests, setPendingRequests] = useState<AuthUser[]>([])
  const [loadingRequests, setLoadingRequests] = useState(false)

  const loadAccessRequests = useCallback(async () => {
    setLoadingRequests(true)
    try {
      const res = await api.getAccessRequests()
      setPendingRequests(res.requests || [])
    } catch {
      // ignore
    } finally {
      setLoadingRequests(false)
    }
  }, [])

  useEffect(() => {
    void loadAccessRequests()
  }, [loadAccessRequests])

  const handleApproveRequest = async (userId: string, uname: string) => {
    try {
      await api.approveAccessRequest(userId)
      toast.success(`Acceso aprobado con éxito para el usuario '${uname}'.`, 'Aprobado')
      void loadAccessRequests()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : 'Error al aprobar la solicitud de acceso',
        'Error',
      )
    }
  }

  const handleRejectRequest = async (userId: string, uname: string) => {
    try {
      await api.rejectAccessRequest(userId)
      toast.info(`Solicitud rechazada para el usuario '${uname}'.`, 'Rechazado')
      void loadAccessRequests()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : 'Error al rechazar la solicitud de acceso',
        'Error',
      )
    }
  }

  return {
    pendingRequests,
    loadingRequests,
    loadAccessRequests,
    handleApproveRequest,
    handleRejectRequest,
  }
}

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../../api/client'
import type { IntegrationInfo } from '../../../types'
import { useToast } from '../../../context/ToastContext'

export function useIntegrationsManager() {
  const { toast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()

  const [integrations, setIntegrations] = useState<IntegrationInfo[]>([])
  const [loadingIntegrations, setLoadingIntegrations] = useState(true)
  const [busyIntegrationId, setBusyIntegrationId] = useState<string | null>(null)

  const loadIntegrations = useCallback(async () => {
    setLoadingIntegrations(true)
    try {
      const items = await api.getIntegrations()
      setIntegrations(items)
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Error al cargar las integraciones'
      toast.error(errMsg)
    } finally {
      setLoadingIntegrations(false)
    }
  }, [toast])

  useEffect(() => {
    void loadIntegrations()
  }, [loadIntegrations])

  // OAuth callbacks listener
  useEffect(() => {
    const handleCallback = (key: 'jira' | 'github' | 'gitlab', label: string) => {
      const status = searchParams.get(key)
      const rawMessage = searchParams.get('message')
      if (status === 'connected') {
        toast.success(`${label} conectado exitosamente. Datos en vivo sincronizados.`)
        setSearchParams({ tab: 'integrations' }, { replace: true })
        void loadIntegrations()
      } else if (status === 'error') {
        const decoded = rawMessage ? decodeURIComponent(rawMessage) : `Error en OAuth de ${label}.`
        const err =
          key === 'jira'
            ? `${decoded} Si Atlassian mostró "Something went wrong" al aceptar, verifica los permisos en la consola de desarrollador de Atlassian o conéctate con Personal Access Token.`
            : decoded
        toast.error(err)
        setSearchParams({ tab: 'integrations' }, { replace: true })
      }
    }
    handleCallback('jira', 'Jira')
    handleCallback('github', 'GitHub')
    handleCallback('gitlab', 'GitLab')
  }, [searchParams, setSearchParams, loadIntegrations, toast])

  const handlePatConnected = async (id: string, label: string) => {
    try {
      await api.syncIntegration(id)
      toast.success(`${label} conectado. Datos sincronizados.`)
    } catch {
      toast.success(`${label} conectado. Selecciona proyectos o repositorios para sincronizar.`)
    }
    await loadIntegrations()
  }

  const handleOAuthConnect = async (id: string) => {
    setBusyIntegrationId(id)
    try {
      const result = await api.startOAuth(id)
      window.location.href = result.authorization_url
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo iniciar el flujo OAuth')
      setBusyIntegrationId(null)
    }
  }

  const handleDisconnect = async (id: string) => {
    setBusyIntegrationId(id)
    try {
      await api.disconnectIntegration(id)
      toast.info(`${id.toUpperCase()} desconectado. Credenciales locales eliminadas.`)
      await loadIntegrations()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al desconectar integración')
    } finally {
      setBusyIntegrationId(null)
    }
  }

  const handleTest = async (id: string) => {
    setBusyIntegrationId(id)
    try {
      const result = await api.testIntegration(id)
      if (result.ok) {
        toast.success(result.message)
      } else {
        toast.error(result.message)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al verificar la conexión')
    } finally {
      setBusyIntegrationId(null)
    }
  }

  const jira = useMemo(() => integrations.find((item) => item.id === 'jira'), [integrations])
  const github = useMemo(() => integrations.find((item) => item.id === 'github'), [integrations])
  const gitlab = useMemo(() => integrations.find((item) => item.id === 'gitlab'), [integrations])

  const connectedCount = useMemo(
    () => integrations.filter((i) => i.status === 'connected').length,
    [integrations],
  )

  return {
    integrations,
    loadingIntegrations,
    busyIntegrationId,
    loadIntegrations,
    handlePatConnected,
    handleOAuthConnect,
    handleDisconnect,
    handleTest,
    jira,
    github,
    gitlab,
    connectedCount,
  }
}

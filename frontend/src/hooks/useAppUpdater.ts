import { useEffect, useState, useCallback, useRef } from 'react'
import { useToast } from '../context/ToastContext'

export interface UpdateInfo {
  version: string
  available: boolean
  url?: string
  releaseNotes?: string
  date?: string
}

interface TauriUpdaterInstance {
  available: boolean
  version?: string
  body?: string
  date?: string
  downloadAndInstall?: () => Promise<void>
}

interface TauriUpdaterModule {
  check?: () => Promise<TauriUpdaterInstance | null>
  checkUpdate?: () => Promise<{
    shouldUpdate: boolean
    manifest?: {
      version: string
      body?: string
      date?: string
    }
  }>
  installUpdate?: () => Promise<void>
}

interface TauriProcessModule {
  relaunch?: () => Promise<void>
}

export function useAppUpdater() {
  const { toast } = useToast()
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null)
  const [isChecking, setIsChecking] = useState(false)
  const [isInstalling, setIsInstalling] = useState(false)
  const isCheckingRef = useRef(false)

  const isTauriEnv = useCallback(() => {
    return (
      typeof window !== 'undefined' &&
      (('__TAURI__' in window && Boolean((window as unknown as { __TAURI__: unknown }).__TAURI__)) ||
        ('__TAURI_INTERNALS__' in window &&
          Boolean((window as unknown as { __TAURI_INTERNALS__: unknown }).__TAURI_INTERNALS__)))
    )
  }, [])

  const loadUpdaterModule = async (): Promise<TauriUpdaterModule | null> => {
    const globalWin = window as unknown as {
      __TAURI__?: {
        updater?: TauriUpdaterModule
      }
    }

    if (globalWin.__TAURI__?.updater) {
      return globalWin.__TAURI__.updater
    }

    try {
      // Dynamic import for Tauri v2 plugin environment
      const importDynamic = new Function('modulePath', 'return import(modulePath)')
      const mod = (await importDynamic('@tauri-apps/plugin-updater')) as TauriUpdaterModule
      return mod
    } catch {
      return null
    }
  }

  const loadProcessModule = async (): Promise<TauriProcessModule | null> => {
    const globalWin = window as unknown as {
      __TAURI__?: {
        process?: TauriProcessModule
      }
    }

    if (globalWin.__TAURI__?.process) {
      return globalWin.__TAURI__.process
    }

    try {
      const importDynamic = new Function('modulePath', 'return import(modulePath)')
      const mod = (await importDynamic('@tauri-apps/plugin-process')) as TauriProcessModule
      return mod
    } catch {
      return null
    }
  }

  const checkForUpdates = useCallback(async (manual = false) => {
    if (!isTauriEnv()) {
      if (manual) {
        toast.info('La comprobación de actualizaciones está disponible en la versión de escritorio.')
      }
      return
    }

    if (isCheckingRef.current) return
    isCheckingRef.current = true
    setIsChecking(true)

    try {
      const updaterModule = await loadUpdaterModule()
      if (!updaterModule) {
        if (manual) {
          toast.info('Módulo de actualización no disponible.')
        }
        return
      }

      if (typeof updaterModule.check === 'function') {
        const update = await updaterModule.check()
        if (update?.available) {
          const version = update.version || 'Nueva versión'
          const stored = localStorage.getItem('qa_mgmt_update_dismissed')
          if (stored === version && !manual) return

          setUpdateInfo({
            version,
            available: true,
            releaseNotes: update.body,
            date: update.date,
          })
          toast.info(`¡Nueva versión ${version} disponible!`, 'Actualización')
        } else if (manual) {
          toast.success('Ya tienes instalada la versión más reciente.', 'Actualizado')
        }
      } else if (typeof updaterModule.checkUpdate === 'function') {
        const result = await updaterModule.checkUpdate()
        if (result?.shouldUpdate) {
          const version = result.manifest?.version || 'Nueva versión'
          const stored = localStorage.getItem('qa_mgmt_update_dismissed')
          if (stored === version && !manual) return

          setUpdateInfo({
            version,
            available: true,
            releaseNotes: result.manifest?.body,
            date: result.manifest?.date,
          })
          toast.info(`¡Nueva versión ${version} disponible!`, 'Actualización')
        } else if (manual) {
          toast.success('Ya tienes instalada la versión más reciente.', 'Actualizado')
        }
      }
    } catch (error) {
      console.warn('Comprobación de actualización omitida o fallida:', error)
      if (manual) {
        toast.error('No se pudo verificar la actualización en este momento.')
      }
    } finally {
      setIsChecking(false)
      isCheckingRef.current = false
    }
  }, [isTauriEnv, toast])

  useEffect(() => {
    // Check after slight delay on launch
    const timeout = setTimeout(() => {
      void checkForUpdates(false)
    }, 3000)

    // Check periodically (every 6 hours)
    const interval = setInterval(() => {
      void checkForUpdates(false)
    }, 6 * 60 * 60 * 1000)

    return () => {
      clearTimeout(timeout)
      clearInterval(interval)
    }
  }, [checkForUpdates])

  const handleInstallUpdate = async () => {
    setIsInstalling(true)
    try {
      toast.info('Descargando e instalando actualización...', 'Actualizando')
      const updaterModule = await loadUpdaterModule()
      const processModule = await loadProcessModule()

      if (updaterModule && typeof updaterModule.installUpdate === 'function') {
        await updaterModule.installUpdate()
        if (processModule && typeof processModule.relaunch === 'function') {
          await processModule.relaunch()
        }
      } else if (updaterModule && typeof updaterModule.check === 'function') {
        const update = await updaterModule.check()
        if (update?.available && typeof update.downloadAndInstall === 'function') {
          await update.downloadAndInstall()
          if (processModule && typeof processModule.relaunch === 'function') {
            await processModule.relaunch()
          }
        }
      } else {
        toast.error('No se pudo invocar el instalador de la actualización.')
      }
    } catch (error) {
      console.error('Error al instalar la actualización:', error)
      toast.error('Ocurrió un error al intentar instalar la actualización.')
    } finally {
      setIsInstalling(false)
    }
  }

  const dismissUpdate = () => {
    if (updateInfo?.version) {
      localStorage.setItem('qa_mgmt_update_dismissed', updateInfo.version)
      setUpdateInfo(null)
    }
  }

  return {
    updateInfo,
    isChecking,
    isInstalling,
    isUpdateAvailable: updateInfo?.available || false,
    checkForUpdates: () => checkForUpdates(true),
    installUpdate: handleInstallUpdate,
    dismissUpdate,
  }
}

import React, { createContext, useContext, useEffect, useState, useTransition } from 'react'
import { useLocation } from 'react-router-dom'

interface LoadingContextValue {
  isLoading: boolean
  startLoading: () => void
  stopLoading: () => void
  withLoading: <T>(action: () => Promise<T>) => Promise<T>
}

const LoadingContext = createContext<LoadingContextValue>({
  isLoading: false,
  startLoading: () => {},
  stopLoading: () => {},
  withLoading: async (fn) => fn(),
})

export const LoadingProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activeRequests, setActiveRequests] = useState(0)
  const [, startTransition] = useTransition()
  const location = useLocation()

  // Trigger top bar briefly on route navigation
  useEffect(() => {
    setActiveRequests((prev) => prev + 1)
    const timer = setTimeout(() => {
      startTransition(() => {
        setActiveRequests((prev) => Math.max(0, prev - 1))
      })
    }, 280)
    return () => clearTimeout(timer)
  }, [location.pathname, location.search])

  const startLoading = () => setActiveRequests((prev) => prev + 1)
  const stopLoading = () => setActiveRequests((prev) => Math.max(0, prev - 1))

  const withLoading = async <T,>(action: () => Promise<T>): Promise<T> => {
    startLoading()
    try {
      return await action()
    } finally {
      stopLoading()
    }
  }

  return (
    <LoadingContext.Provider
      value={{
        isLoading: activeRequests > 0,
        startLoading,
        stopLoading,
        withLoading,
      }}
    >
      {/* Top progress bar with brand gradient */}
      <div
        className={`fixed top-0 left-0 right-0 z-50 pointer-events-none transition-opacity duration-300 ${
          activeRequests > 0 ? 'opacity-100' : 'opacity-0'
        }`}
        aria-hidden="true"
      >
        <div className="h-0.5 w-full bg-gradient-to-r from-[#002777] via-[#004497] to-cyan-400 animate-shimmer" />
      </div>
      {children}
    </LoadingContext.Provider>
  )
}

export const usePageLoading = (): LoadingContextValue => useContext(LoadingContext)

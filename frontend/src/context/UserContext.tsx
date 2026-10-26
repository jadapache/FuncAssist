import { createContext, useContext, type ReactNode } from 'react'
import { api, type UserProfile, type UserRole } from '../api/client'
import { useAuth } from './AuthContext'

export type { UserRole, UserProfile }

interface UserContextType {
  user: UserProfile | null
  isLoading: boolean
  isFirstTimeSetup: boolean
  updateProfile: (profile: Partial<UserProfile>) => Promise<void>
  completeSetup: (profile: UserProfile) => Promise<void>
}

const UserContext = createContext<UserContextType | undefined>(undefined)

export const UserProvider = ({ children }: { children: ReactNode }) => {
  const { user: authUser, isLoading, updateUser } = useAuth()

  const userProfile: UserProfile | null = authUser
    ? {
        display_name: authUser.full_name || authUser.username,
        user_role: (authUser.role as UserRole) || 'funcional',
      }
    : null

  const updateProfile = async (updates: Partial<UserProfile>) => {
    if (!authUser) return
    const res = await api.updateProfile({
      full_name: updates.display_name,
    })
    updateUser(res.user)
  }

  const completeSetup = async (_profile: UserProfile) => {
    // Kept for backward compatibility
  }

  return (
    <UserContext.Provider
      value={{
        user: userProfile,
        isLoading,
        isFirstTimeSetup: false,
        updateProfile,
        completeSetup,
      }}
    >
      {children}
    </UserContext.Provider>
  )
}

export const useUser = () => {
  const context = useContext(UserContext)
  if (!context) throw new Error('useUser must be used within UserProvider')
  return context
}

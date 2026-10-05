import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, type UserProfile, type UserRole } from '../api/client'

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
  const [user, setUser] = useState<UserProfile | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isFirstTimeSetup, setIsFirstTimeSetup] = useState(false)

  useEffect(() => {
    const loadUser = async () => {
      try {
        localStorage.removeItem('qa_mgmt_auth_token')
        const profile = await api.getUserProfile()

        // Check if this is first-time setup (display_name is default or empty)
        if (!profile.display_name || profile.display_name === 'Usuario') {
          setIsFirstTimeSetup(true)
        } else {
          setUser(profile)
        }
      } catch (error) {
        console.error('Error loading user profile:', error)
        setIsFirstTimeSetup(true)
      } finally {
        setIsLoading(false)
      }
    }

    void loadUser()
  }, [])

  const updateProfile = async (updates: Partial<UserProfile>) => {
    const updated = await api.updateUserProfile(updates)
    setUser(updated)
  }

  const completeSetup = async (profile: UserProfile) => {
    const created = await api.setupUser(profile)
    setUser(created)
    setIsFirstTimeSetup(false)
  }

  return (
    <UserContext.Provider value={{ user, isLoading, isFirstTimeSetup, updateProfile, completeSetup }}>
      {children}
    </UserContext.Provider>
  )
}

export const useUser = () => {
  const context = useContext(UserContext)
  if (!context) throw new Error('useUser must be used within UserProvider')
  return context
}

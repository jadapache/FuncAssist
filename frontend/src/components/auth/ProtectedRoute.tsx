import { Navigate, Outlet } from 'react-router-dom'
import { useUser, type UserRole } from '../../context/UserContext'
import { FirstTimeSetup } from '../../features/setup'

interface ProtectedRouteProps {
  allowedRoles?: UserRole[]
}

export const ProtectedRoute = ({ allowedRoles }: ProtectedRouteProps) => {
  const { user, isLoading, isFirstTimeSetup } = useUser()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4" />
          <p className="text-slate-600 font-medium">Cargando...</p>
        </div>
      </div>
    )
  }

  if (isFirstTimeSetup) {
    return <FirstTimeSetup />
  }

  if (allowedRoles && user && !allowedRoles.includes(user.user_role)) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

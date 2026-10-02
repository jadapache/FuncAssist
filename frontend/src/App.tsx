import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/AppLayout'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { ToastContainer } from './components/common/Toast'
import { AuthProvider } from './context/AuthContext'
import { ToastProvider } from './context/ToastContext'
import { ErrorBoundary } from './core/providers/ErrorBoundary'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { AskProductPage } from './pages/conocimiento/AskProductPage'
import { KnowledgePage } from './pages/conocimiento/KnowledgePage'
import { ProfilePage } from './pages/configuraciones/ProfilePage'
import { SettingsPage } from './pages/configuraciones/SettingsPage'
import { LevantamientoPage } from './pages/funcional/LevantamientoPage'
import { MejorasPage } from './pages/funcional/MejorasPage'
import { InventarioPage } from './pages/funcional/InventarioPage'
import { TranscripcionesPage } from './pages/funcional/TranscripcionesPage'
import { FuncionalFeaturePage } from './pages/funcional/FuncionalFeaturePage'
import { PmFeaturePage } from './pages/pm/PmFeaturePage'
import { StandupPage } from './pages/pm/StandupPage'
import { QaFeaturePage } from './pages/qa/QaFeaturePage'

export const App = () => {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <AuthProvider>
          <BrowserRouter>
            <ToastContainer />
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<ProtectedRoute />}>
                <Route element={<AppLayout />}>
                  <Route index element={<DashboardPage />} />
                  <Route path="pm/standup" element={<StandupPage />} />
                  <Route path="pm/:slug" element={<PmFeaturePage />} />
                  <Route path="funcional/transcripciones" element={<TranscripcionesPage />} />
                  <Route path="funcional/inventario" element={<InventarioPage />} />
                  <Route path="funcional/levantamiento" element={<LevantamientoPage />} />
                  <Route path="funcional/mejoras" element={<MejorasPage />} />
                  <Route path="funcional/:slug" element={<FuncionalFeaturePage />} />
                  <Route path="qa/:slug" element={<QaFeaturePage />} />
                  <Route path="knowledge" element={<KnowledgePage />} />
                  <Route path="knowledge/ask" element={<AskProductPage />} />
                  <Route path="integrations" element={<Navigate to="/settings?tab=integrations" replace />} />
                  <Route path="profile" element={<ProfilePage />} />
                  <Route path="settings" element={<SettingsPage />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Route>
              </Route>
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ToastProvider>
    </ErrorBoundary>
  )
}

export default App

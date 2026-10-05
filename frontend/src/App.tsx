import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/AppLayout'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { ToastContainer } from './components/common/Toast'
import { UserProvider } from './context/UserContext'
import { ToastProvider } from './context/ToastContext'
import { ErrorBoundary } from './core/providers/ErrorBoundary'
import { DashboardPage } from './pages/DashboardPage'
import { AskProductPage } from './pages/conocimiento/AskProductPage'
import { KnowledgePage } from './pages/conocimiento/KnowledgePage'
import { ProfilePage } from './pages/configuraciones/ProfilePage'
import { SettingsPage } from './pages/configuraciones/SettingsPage'
import { LevantamientoPage } from './pages/funcional/LevantamientoPage'
import { MejorasPage } from './pages/funcional/MejorasPage'
import { InventarioPage } from './pages/funcional/InventarioPage'
import { TranscripcionesPage } from './features/transcription/pages/TranscripcionesPage'
import { FuncionalFeaturePage } from './pages/funcional/FuncionalFeaturePage'
import { PmFeaturePage } from './pages/pm/PmFeaturePage'
import { StandupPage } from './pages/pm/StandupPage'
import { QaFeaturePage } from './pages/qa/QaFeaturePage'

export const App = () => {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <UserProvider>
          <BrowserRouter>
            <ToastContainer />
            <Routes>
              <Route element={<ProtectedRoute />}>
                <Route element={<AppLayout />}>
                  {/* Dashboard - all roles */}
                  <Route index element={<DashboardPage />} />

                  {/* PM Routes - admin, pm */}
                  <Route element={<ProtectedRoute allowedRoles={['admin', 'pm']} />}>
                    <Route path="pm/standup" element={<StandupPage />} />
                    <Route path="pm/:slug" element={<PmFeaturePage />} />
                  </Route>

                  {/* Funcional Routes - admin, funcional */}
                  <Route element={<ProtectedRoute allowedRoles={['admin', 'funcional']} />}>
                    <Route path="funcional/transcripciones" element={<TranscripcionesPage />} />
                    <Route path="funcional/inventario" element={<InventarioPage />} />
                    <Route path="funcional/levantamiento" element={<LevantamientoPage />} />
                    <Route path="funcional/mejoras" element={<MejorasPage />} />
                    <Route path="funcional/:slug" element={<FuncionalFeaturePage />} />
                  </Route>

                  {/* QA Routes - admin, qa */}
                  <Route element={<ProtectedRoute allowedRoles={['admin', 'qa']} />}>
                    <Route path="qa/:slug" element={<QaFeaturePage />} />
                  </Route>

                  {/* Knowledge Routes - admin, pm, dev, qa, funcional */}
                  <Route element={<ProtectedRoute allowedRoles={['admin', 'pm', 'qa', 'funcional']} />}>
                    <Route path="knowledge" element={<KnowledgePage />} />
                    <Route path="knowledge/ask" element={<AskProductPage />} />
                  </Route>

                  <Route path="integrations" element={<Navigate to="/settings?tab=integrations" replace />} />
                  <Route path="profile" element={<ProfilePage />} />
                  <Route path="settings" element={<SettingsPage />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Route>
              </Route>
            </Routes>
          </BrowserRouter>
        </UserProvider>
      </ToastProvider>
    </ErrorBoundary>
  )
}

export default App

import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/AppLayout'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { ToastContainer } from './components/common/Toast'
import { FloatingJobToast } from './components/common/FloatingJobToast'
import { AuthProvider } from './context/AuthContext'
import { UserProvider } from './context/UserContext'
import { ToastProvider } from './context/ToastContext'
import { BackgroundJobProvider, useBackgroundJobs } from './context/BackgroundJobContext'
import { TranscriptionProvider } from './features/transcription'
import { ErrorBoundary } from './core/providers/ErrorBoundary'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { KnowledgePage, AskProductPage } from './features/knowledge'
import { SettingsPage, ProfilePage } from './features/settings'
import {
  MejorasPage,
  LevantamientoPage,
  InventarioPage,
  FuncionalFeaturePage,
} from './features/funcional'
import { TranscripcionesPage } from './features/transcription'
import { StandupPage, PmFeaturePage } from './features/pm'
import { QaFeaturePage } from './features/qa'



const GlobalFloatingJobs: React.FC = () => {
  const { jobs, cancelJob, removeJob } = useBackgroundJobs()
  return (
    <FloatingJobToast
      jobs={jobs}
      onCancelJob={(id) => void cancelJob(id)}
      onDismissJob={(id) => removeJob(id)}
    />
  )
}

export const App = () => {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <AuthProvider>
          <UserProvider>
            <BrowserRouter>
              <BackgroundJobProvider>
                <TranscriptionProvider>
                  <ToastContainer />
                  <GlobalFloatingJobs />
                  <Routes>
                    {/* Public Route */}
                    <Route path="login" element={<LoginPage />} />

                    {/* Protected Authenticated Routes */}
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
                </TranscriptionProvider>
              </BackgroundJobProvider>
            </BrowserRouter>
          </UserProvider>
        </AuthProvider>
      </ToastProvider>
    </ErrorBoundary>
  )
}

export default App

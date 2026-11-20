import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/misc'
import { AuthProvider } from '@/context/AuthContext'
import { AppLayout } from '@/layouts/AppLayout'
import { AdaptiveLayout, PublicLayout } from '@/layouts/PublicLayout'
import Landing from '@/pages/Landing'
import Login from '@/pages/auth/Login'
import { ForgotPassword, ResetPassword } from '@/pages/auth/PasswordReset'
import Register from '@/pages/auth/Register'

// Pages with charts or long content are code-split so the landing and sign-in pages stay small
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const HealthCheck = lazy(() => import('@/pages/HealthCheck'))
const Explainability = lazy(() => import('@/pages/Explainability'))
const Assistant = lazy(() => import('@/pages/Assistant'))
const RagEvaluation = lazy(() => import('@/pages/RagEvaluation'))
const Reports = lazy(() => import('@/pages/Reports'))
const Locator = lazy(() => import('@/pages/Locator'))
const Reminders = lazy(() => import('@/pages/Reminders'))
const Settings = lazy(() => import('@/pages/Settings'))
const Learn = lazy(() => import('@/pages/Learn'))
const Help = lazy(() => import('@/pages/Help'))
const AccuracyPage = lazy(() => import('@/pages/AnalyticsDetails').then((m) => ({ default: m.AccuracyPage })))
const GroupsPage = lazy(() => import('@/pages/AnalyticsDetails').then((m) => ({ default: m.GroupsPage })))
const Privacy = lazy(() => import('@/pages/Legal').then((m) => ({ default: m.Privacy })))
const Terms = lazy(() => import('@/pages/Legal').then((m) => ({ default: m.Terms })))

const fallback = (
  <div className="grid min-h-[50vh] place-items-center text-muted-foreground">
    <Spinner className="size-6" />
  </div>
)

function NotFound() {
  return (
    <div className="grid min-h-[60vh] place-items-center px-4 text-center">
      <div className="space-y-3">
        <p className="text-sm font-semibold text-teal">404</p>
        <h1 className="text-2xl font-semibold text-primary">We could not find that page</h1>
        <p className="text-muted-foreground">The link may be old or mistyped.</p>
        <Button asChild>
          <Link to="/">Go to the home page</Link>
        </Button>
      </div>
    </div>
  )
}

/** Opens each new page at the top, like a normal website. */
function ScrollToTop() {
  const { pathname, hash } = useLocation()
  useEffect(() => {
    if (!hash) window.scrollTo(0, 0)
  }, [pathname, hash])
  return null
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ScrollToTop />
        <Suspense fallback={fallback}>
          <Routes>
            <Route element={<PublicLayout />}>
              <Route path="/" element={<Landing />} />
            </Route>
            <Route element={<AdaptiveLayout />}>
              <Route path="/learn" element={<Learn />} />
              <Route path="/help" element={<Help />} />
              <Route path="/privacy" element={<Privacy />} />
              <Route path="/terms" element={<Terms />} />
            </Route>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<AppLayout />}>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/assistant" element={<Assistant />} />
                <Route path="/reports" element={<Reports />} />
                <Route path="/analytics" element={<HealthCheck />} />
                <Route path="/locator" element={<Locator />} />
                <Route path="/reminders" element={<Reminders />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/learn/accuracy" element={<AccuracyPage />} />
                <Route path="/learn/groups" element={<GroupsPage />} />
                <Route path="/explainability" element={<Explainability />} />
                <Route path="/assistant/evaluation" element={<RagEvaluation />} />
              </Route>
            </Route>
            <Route path="/health-check" element={<Navigate to="/analytics" replace />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  )
}

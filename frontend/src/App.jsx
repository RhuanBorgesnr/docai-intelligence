import React, { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { auth } from './services/api'

// Client product pages (SaaS — visible to all authenticated users)
import Login from './pages/Login'
import Register from './pages/Register'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import VerifyEmail from './pages/VerifyEmail'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import Chat from './pages/Chat'
import Indicators from './pages/Indicators'
import Charts from './pages/Charts'
import Compare from './pages/Compare'
import Clauses from './pages/Clauses'
import Settings from './pages/Settings'
import Integrations from './pages/Integrations'

// Ops internal pages (visible only to staff/ops users)
import OpsCockpit from './pages/OpsCockpit'
import Leads from './pages/Leads'
import Pipeline from './pages/Pipeline'
import JarvisPanel from './pages/JarvisPanel'
import Operations from './pages/Operations'
import OpsAgentTeam from './pages/OpsAgentTeam'
import OpsApprovals from './pages/OpsApprovals'

// Layouts
import ClientLayout from './components/ClientLayout'
import OpsLayout, { OpsGuard } from './components/OpsLayout'

// Lazy pages
const LeadDetail = lazy(() => import('./pages/LeadDetail'))

// ── Guards ────────────────────────────────────────────────────────────────────

function ProtectedRoute({ children }) {
  const location = useLocation()
  if (!auth.isAuthenticated()) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  return children
}

/** Shorthand: ProtectedRoute + ClientLayout wrapper */
function Client({ children }) {
  return <ProtectedRoute><ClientLayout>{children}</ClientLayout></ProtectedRoute>
}

/** Shorthand: OpsGuard + OpsLayout wrapper */
function Ops({ children }) {
  return <OpsGuard><OpsLayout>{children}</OpsLayout></OpsGuard>
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password/:uid/:token" element={<ResetPassword />} />
      <Route path="/verify-email/:uid/:token" element={<VerifyEmail />} />

      {/* ─── Client product (/app/*) ─────────────────────────────────────── */}
      <Route path="/app"              element={<Client><Dashboard /></Client>} />
      <Route path="/app/upload"       element={<Client><Upload /></Client>} />
      <Route path="/app/chat/:id"     element={<Client><Chat /></Client>} />
      <Route path="/app/indicators/:id" element={<Client><Indicators /></Client>} />
      <Route path="/app/charts"       element={<Client><Charts /></Client>} />
      <Route path="/app/compare"      element={<Client><Compare /></Client>} />
      <Route path="/app/clauses/:id"  element={<Client><Clauses /></Client>} />
      <Route path="/app/settings"     element={<Client><Settings /></Client>} />
      <Route path="/app/integrations" element={<Client><Integrations /></Client>} />

      {/* ─── Ops internal (/ops/*) ───────────────────────────────────────── */}
      <Route path="/ops"              element={<Ops><OpsCockpit /></Ops>} />
      <Route path="/ops/leads"        element={<Ops><Leads /></Ops>} />
      <Route path="/ops/leads/:leadId" element={<Ops><Suspense fallback={<div className="p-6 text-gray-400">Carregando…</div>}><LeadDetail /></Suspense></Ops>} />
      <Route path="/ops/pipeline"     element={<Ops><Pipeline /></Ops>} />
      <Route path="/ops/theo"         element={<Ops><JarvisPanel /></Ops>} />
      <Route path="/ops/operations"   element={<Ops><Operations /></Ops>} />
      <Route path="/ops/team"          element={<Ops><OpsAgentTeam /></Ops>} />
      <Route path="/ops/approvals"     element={<Ops><OpsApprovals /></Ops>} />


      {/* ─── Redirects ───────────────────────────────────────────────────── */}
      {/* Root → /app for clients, /ops for staff (simplified: → /app always) */}
      <Route path="/" element={<RootRedirect />} />

      {/* Legacy routes → new locations */}
      <Route path="/upload"     element={<Navigate to="/app/upload" replace />} />
      <Route path="/charts"     element={<Navigate to="/app/charts" replace />} />
      <Route path="/compare"    element={<Navigate to="/app/compare" replace />} />
      <Route path="/settings"   element={<Navigate to="/app/settings" replace />} />
      <Route path="/leads"      element={<Navigate to="/ops/leads" replace />} />
      <Route path="/pipeline"   element={<Navigate to="/ops/pipeline" replace />} />
      <Route path="/jarvis"     element={<Navigate to="/ops/theo" replace />} />
      <Route path="/operations" element={<Navigate to="/ops/operations" replace />} />

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

/** Root / redirects staff → /ops, others → /app */
function RootRedirect() {
  const user = auth.getUser()
  if (user && user.is_staff !== false) {
    return <Navigate to="/ops" replace />
  }
  return <Navigate to="/app" replace />
}

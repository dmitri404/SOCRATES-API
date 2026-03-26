import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import AppLayout from '@/layouts/AppLayout'
import Login from '@/pages/Login'
import Dashboard from '@/pages/Dashboard'
import PortalLayout from '@/pages/portais/PortalLayout'
import ConfGeral from '@/pages/portais/ConfGeral'
import ConfCredores from '@/pages/portais/ConfCredores'
import ConfEmails from '@/pages/portais/ConfEmails'
import ConfExercicios from '@/pages/portais/ConfExercicios'
import ConfCron from '@/pages/portais/ConfCron'
import Trigger from '@/pages/portais/Trigger'
import Perfil from '@/pages/Perfil'
import Usuarios from '@/pages/admin/Usuarios'

function RequireAuth() {
  const token = useAuthStore((s) => s.token)
  return token ? <Outlet /> : <Navigate to="/login" replace />
}

function RequireRole({ roles }: { roles: string[] }) {
  const user = useAuthStore((s) => s.user)
  return !user || !roles.includes(user.role)
    ? <Navigate to="/dashboard" replace />
    : <Outlet />
}

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: '/', element: <Navigate to="/dashboard" replace /> },
          { path: '/dashboard', element: <Dashboard /> },
          { path: '/perfil', element: <Perfil /> },
          {
            path: '/portais/:slug',
            element: <PortalLayout />,
            children: [
              { index: true, element: <Navigate to="geral" replace /> },
              { path: 'geral',      element: <ConfGeral /> },
              { path: 'credores',   element: <ConfCredores /> },
              { path: 'emails',     element: <ConfEmails /> },
              { path: 'exercicios', element: <ConfExercicios /> },
              {
                element: <RequireRole roles={['admin', 'supervisor']} />,
                children: [
                  { path: 'cron',     element: <ConfCron /> },
                  { path: 'trigger',  element: <Trigger /> },
                ],
              },
            ],
          },
          {
            element: <RequireRole roles={['admin', 'supervisor']} />,
            children: [
              { path: '/admin/usuarios', element: <Usuarios /> },
            ],
          },
        ],
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])

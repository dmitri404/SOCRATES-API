import { useEffect } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import { logout as apiLogout, me } from '@/api/auth'
import { LayoutDashboard, Settings, Users, LogOut, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function AppLayout() {
  const { user, setUser, logout } = useAuthStore()
  const navigate = useNavigate()

  // Atualiza dados do usuário (portais, role) a cada montagem do app
  useEffect(() => {
    me().then(setUser).catch(() => {})
  }, [])

  const handleLogout = async () => {
    try { await apiLogout() } catch {}
    logout()
    navigate('/login')
  }

  const navLink = (to: string, label: string, icon: React.ReactNode) => (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn('flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors',
          isActive ? 'bg-blue-700 text-white' : 'text-slate-300 hover:bg-slate-700 hover:text-white')
      }
    >
      {icon}
      {label}
    </NavLink>
  )

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-60 bg-slate-800 flex flex-col">
        <div className="px-4 py-5 border-b border-slate-700">
          <h1 className="text-white font-bold text-lg">SOCRATES</h1>
          <p className="text-slate-400 text-xs mt-0.5">{user?.nome}</p>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navLink('/dashboard', 'Dashboard', <LayoutDashboard size={16} />)}

          {user?.portais && user.portais.length > 0 && (
            <div className="mt-4">
              <p className="text-slate-500 text-xs uppercase tracking-wider px-3 mb-2">Portais</p>
              {user.portais.map((p) => (
                <NavLink
                  key={p.slug}
                  to={`/portais/${p.slug}`}
                  className={({ isActive }) =>
                    cn('flex items-center justify-between px-3 py-2 rounded-md text-sm transition-colors',
                      isActive ? 'bg-blue-700 text-white' : 'text-slate-300 hover:bg-slate-700 hover:text-white')
                  }
                >
                  <span className="flex items-center gap-2">
                    <Settings size={14} />
                    <span className="truncate">{p.nome}</span>
                  </span>
                  <ChevronRight size={12} />
                </NavLink>
              ))}
            </div>
          )}

          {(user?.role === 'admin' || user?.role === 'supervisor') && (
            <div className="mt-4">
              <p className="text-slate-500 text-xs uppercase tracking-wider px-3 mb-2">Administração</p>
              {navLink('/admin/usuarios', 'Usuários', <Users size={16} />)}
            </div>
          )}
        </nav>

        <div className="px-3 py-4 border-t border-slate-700">
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 px-3 py-2 w-full rounded-md text-sm text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
          >
            <LogOut size={16} />
            Sair
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}

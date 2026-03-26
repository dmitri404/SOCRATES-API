import { NavLink, Outlet, useParams } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import { cn } from '@/lib/utils'

const PORTAIS_COM_POWERBI = ['municipal']

const TABS = [
  { path: 'geral',       label: 'Geral' },
  { path: 'credores',    label: 'Credores' },
  { path: 'emails',      label: 'E-mails' },
  { path: 'exercicios',  label: 'Exercícios' },
  { path: 'cron',        label: 'Cron',      roles: ['admin', 'supervisor'] as string[] },
  { path: 'powerbi',     label: 'Power BI',  portais: PORTAIS_COM_POWERBI },
  { path: 'trigger',     label: 'Executar',  roles: ['admin', 'supervisor'] as string[] },
]

export default function PortalLayout() {
  const { slug } = useParams<{ slug: string }>()
  const { user } = useAuthStore()

  const portalNome = user?.portais.find((p) => p.slug === slug)?.nome ?? slug

  const tabs = TABS.filter((t) => {
    if (t.roles && !t.roles.includes(user?.role ?? '')) return false
    if (t.portais && !t.portais.includes(slug ?? '')) return false
    return true
  })

  return (
    <div className="p-8">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-slate-800">{portalNome}</h2>
      </div>

      <div className="flex gap-1 border-b border-gray-200 mb-6">
        {tabs.map((tab) => (
          <NavLink
            key={tab.path}
            to={`/portais/${slug}/${tab.path}`}
            className={({ isActive }) =>
              cn('px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
                isActive
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700')
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </div>

      <Outlet />
    </div>
  )
}

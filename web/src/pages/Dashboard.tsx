import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import { Settings, Play } from 'lucide-react'
import { Button } from '@/components/ui/button'

const PORTAL_COLORS: Record<string, string> = {
  'municipal':     'bg-blue-50 border-blue-200',
  'estado-am':     'bg-green-50 border-green-200',
  'municipio-pvh': 'bg-orange-50 border-orange-200',
  'estado-ms':     'bg-purple-50 border-purple-200',
  'estado-ro':     'bg-rose-50 border-rose-200',
}

export default function Dashboard() {
  const { user } = useAuthStore()
  const navigate = useNavigate()

  return (
    <div className="p-8">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-slate-800">Dashboard</h2>
        <p className="text-slate-500 text-sm mt-1">Bem-vindo, {user?.nome}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {user?.portais.map((portal) => (
          <div
            key={portal.slug}
            className={`rounded-xl border p-5 ${PORTAL_COLORS[portal.slug] ?? 'bg-gray-50 border-gray-200'}`}
          >
            <h3 className="font-semibold text-slate-700 text-sm">{portal.nome}</h3>
            <p className="text-xs text-slate-500 mt-1 mb-4">
              {portal.pode_editar ? 'Leitura e escrita' : 'Somente leitura'}
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => navigate(`/portais/${portal.slug}`)}
                className="flex items-center gap-1"
              >
                <Settings size={13} />
                Configurar
              </Button>
              {(user.role === 'admin' || user.role === 'supervisor') && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => navigate(`/portais/${portal.slug}/trigger`)}
                  className="flex items-center gap-1"
                >
                  <Play size={13} />
                  Executar
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

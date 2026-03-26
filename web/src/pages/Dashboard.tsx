import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import { Settings, Play, RefreshCw, Server, HardDrive, Cpu, Clock, Database } from 'lucide-react'
import { Button } from '@/components/ui/button'
import api from '@/api/client'

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface LogPortal {
  slug: string
  nome: string
  ultima_exec: string | null
  duracao: string | null
  sucesso: boolean | null
}

interface Saude {
  ram:        { total_gb: number; usado_gb: number; livre_gb: number; percentual: number }
  disco:      { total_gb: number; usado_gb: number; livre_gb: number; percentual: number }
  cpu:        { load_1m: number; load_5m: number; load_15m: number }
  uptime:     { dias: number; horas: number; minutos: number }
  containers: { nome: string; status: string; saudavel: boolean }[]
  postgres:   { tamanho: string; conexoes_ativas: number; versao: string; status: string }
  logs:       LogPortal[]
}

// ── Helpers visuais ────────────────────────────────────────────────────────────

const PORTAL_COLORS: Record<string, string> = {
  municipal:     'bg-blue-50 border-blue-200',
  'estado-am':   'bg-green-50 border-green-200',
  'municipio-pvh':'bg-orange-50 border-orange-200',
  'estado-ms':   'bg-purple-50 border-purple-200',
  'estado-ro':   'bg-rose-50 border-rose-200',
}

function BarraUso({ pct, cor }: { pct: number; cor: string }) {
  return (
    <div className="w-full bg-slate-100 rounded-full h-1.5 mt-2">
      <div className={`h-1.5 rounded-full ${cor}`} style={{ width: `${Math.min(pct, 100)}%` }} />
    </div>
  )
}

function corPct(pct: number) {
  if (pct < 60) return 'bg-green-400'
  if (pct < 85) return 'bg-yellow-400'
  return 'bg-red-500'
}

function CardMetrica({
  icon, titulo, valor, sub, pct,
}: {
  icon: React.ReactNode
  titulo: string
  valor: string
  sub: string
  pct?: number
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 text-slate-400 mb-2">
        {icon}
        <span className="text-xs uppercase tracking-wide font-medium">{titulo}</span>
      </div>
      <p className="text-2xl font-bold text-slate-800">{valor}</p>
      <p className="text-xs text-slate-400 mt-0.5">{sub}</p>
      {pct !== undefined && <BarraUso pct={pct} cor={corPct(pct)} />}
    </div>
  )
}

// ── Componente principal ───────────────────────────────────────────────────────

export default function Dashboard() {
  const { user } = useAuthStore()
  const navigate  = useNavigate()
  const [saude, setSaude]       = useState<Saude | null>(null)
  const [loadingSaude, setLoadingSaude] = useState(false)
  const [ultimaAtualizacao, setUltimaAtualizacao] = useState<Date | null>(null)

  const carregarSaude = useCallback(async () => {
    setLoadingSaude(true)
    try {
      const { data } = await api.get('/admin/saude')
      setSaude(data)
      setUltimaAtualizacao(new Date())
    } catch {}
    finally { setLoadingSaude(false) }
  }, [])

  useEffect(() => {
    carregarSaude()
    const id = setInterval(carregarSaude, 60_000)
    return () => clearInterval(id)
  }, [carregarSaude])

  const { dias, horas, minutos } = saude?.uptime ?? { dias: 0, horas: 0, minutos: 0 }
  const uptimeStr = dias > 0 ? `${dias}d ${horas}h ${minutos}m` : `${horas}h ${minutos}m`

  const containersSaudaveis = saude?.containers.filter((c) => c.saudavel).length ?? 0
  const containersTotal     = saude?.containers.length ?? 0

  return (
    <div className="p-8 space-y-8">

      {/* Cabeçalho */}
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Dashboard</h2>
        <p className="text-slate-500 text-sm mt-1">Bem-vindo, {user?.nome}</p>
      </div>

      {/* Portais */}
      {user?.portais && user.portais.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">Portais</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {user.portais.map((portal) => (
              <div
                key={portal.slug}
                className={`rounded-xl border p-5 ${PORTAL_COLORS[portal.slug] ?? 'bg-gray-50 border-gray-200'}`}
              >
                <h3 className="font-semibold text-slate-700 text-sm">{portal.nome}</h3>
                <p className="text-xs text-slate-500 mt-1 mb-4">
                  {portal.pode_editar ? 'Leitura e escrita' : 'Somente leitura'}
                </p>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => navigate(`/portais/${portal.slug}`)} className="flex items-center gap-1">
                    <Settings size={13} /> Configurar
                  </Button>
                  {(user.role === 'admin' || user.role === 'supervisor') && (
                    <Button size="sm" variant="outline" onClick={() => navigate(`/portais/${portal.slug}/trigger`)} className="flex items-center gap-1">
                      <Play size={13} /> Executar
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Saúde da VPS */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Saúde da VPS</h3>
          <div className="flex items-center gap-3">
            {ultimaAtualizacao && (
              <span className="text-xs text-slate-400">
                Atualizado às {ultimaAtualizacao.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
            )}
            <button
              onClick={carregarSaude}
              disabled={loadingSaude}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-blue-600 transition-colors disabled:opacity-40"
            >
              <RefreshCw size={12} className={loadingSaude ? 'animate-spin' : ''} />
              Atualizar
            </button>
          </div>
        </div>

        {saude ? (
          <div className="space-y-4">
            {/* Métricas */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <CardMetrica
                icon={<Server size={14} />}
                titulo="RAM"
                valor={`${saude.ram.usado_gb} GB`}
                sub={`de ${saude.ram.total_gb} GB — ${saude.ram.percentual}%`}
                pct={saude.ram.percentual}
              />
              <CardMetrica
                icon={<HardDrive size={14} />}
                titulo="Disco"
                valor={`${saude.disco.usado_gb} GB`}
                sub={`de ${saude.disco.total_gb} GB — ${saude.disco.percentual}%`}
                pct={saude.disco.percentual}
              />
              <CardMetrica
                icon={<Cpu size={14} />}
                titulo="Load"
                valor={String(saude.cpu.load_1m)}
                sub={`5m: ${saude.cpu.load_5m} · 15m: ${saude.cpu.load_15m}`}
              />
              <CardMetrica
                icon={<Clock size={14} />}
                titulo="Uptime"
                valor={uptimeStr}
                sub={`${containersSaudaveis}/${containersTotal} containers ativos`}
              />
              <CardMetrica
                icon={<Database size={14} />}
                titulo="PostgreSQL"
                valor={saude.postgres.tamanho ?? '—'}
                sub={`v${saude.postgres.versao} · ${saude.postgres.conexoes_ativas} conexões ativas`}
              />
            </div>

            {/* Logs de execução */}
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Última execução dos scrapers</p>
              </div>
              <div className="divide-y divide-gray-50">
                {saude.logs.map((log) => (
                  <div key={log.slug} className="flex items-center justify-between px-4 py-3">
                    <div>
                      <p className="text-sm font-medium text-slate-700">{log.nome}</p>
                      <p className="text-xs text-slate-400 mt-0.5">
                        {log.ultima_exec
                          ? new Date(log.ultima_exec).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
                          : 'Sem registro'}
                        {log.duracao && <span className="ml-2">· {log.duracao}</span>}
                      </p>
                    </div>
                    <span className={`text-xs font-medium rounded-full px-2.5 py-1 ${
                      log.sucesso === null  ? 'bg-slate-100 text-slate-400' :
                      log.sucesso          ? 'bg-green-100 text-green-700' :
                                             'bg-red-100 text-red-600'
                    }`}>
                      {log.sucesso === null ? 'Sem log' : log.sucesso ? 'Sucesso' : 'Erro'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
            <p className="text-slate-400 text-sm">{loadingSaude ? 'Carregando...' : 'Sem dados'}</p>
          </div>
        )}
      </section>
    </div>
  )
}

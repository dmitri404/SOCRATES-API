import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import api from '@/api/client'
import { Button } from '@/components/ui/button'

const DIAS = [
  { label: 'Seg', value: 1 },
  { label: 'Ter', value: 2 },
  { label: 'Qua', value: 3 },
  { label: 'Qui', value: 4 },
  { label: 'Sex', value: 5 },
  { label: 'Sáb', value: 6 },
  { label: 'Dom', value: 0 },
]

function parseCron(expr: string): { time: string; days: number[] } {
  const parts = expr.trim().split(/\s+/)
  if (parts.length !== 5) return { time: '10:00', days: [1, 2, 3, 4, 5] }

  const [min, hour, , , dow] = parts

  let days: number[] = []
  if (dow === '*') {
    days = [0, 1, 2, 3, 4, 5, 6]
  } else {
    for (const seg of dow.split(',')) {
      if (seg.includes('-')) {
        const [start, end] = seg.split('-').map(Number)
        for (let i = start; i <= end; i++) days.push(i % 7)
      } else {
        days.push(Number(seg) % 7)
      }
    }
    days = [...new Set(days)].sort((a, b) => a - b)
  }

  return {
    time: `${String(parseInt(hour, 10)).padStart(2, '0')}:${String(parseInt(min, 10)).padStart(2, '0')}`,
    days,
  }
}

function buildCron(time: string, days: number[]): string {
  const [h, m] = time.split(':')
  const hour = parseInt(h, 10)
  const minute = parseInt(m, 10)

  if (days.length === 0 || days.length === 7) {
    return `${minute} ${hour} * * *`
  }

  const sorted = [...days].sort((a, b) => a - b)
  const ranges: string[] = []
  let i = 0
  while (i < sorted.length) {
    let j = i
    while (j + 1 < sorted.length && sorted[j + 1] === sorted[j] + 1) j++
    ranges.push(j > i ? `${sorted[i]}-${sorted[j]}` : String(sorted[i]))
    i = j + 1
  }

  return `${minute} ${hour} * * ${ranges.join(',')}`
}

function descricao(time: string, days: number[]): string {
  const labels = DIAS.filter((d) => days.includes(d.value)).map((d) => d.label)
  if (labels.length === 0) return 'Nenhum dia selecionado'
  const diasStr =
    days.length === 7
      ? 'todos os dias'
      : labels.length === 5 && !days.includes(0) && !days.includes(6)
      ? 'dias úteis'
      : labels.join(', ')
  return `Todo(a) ${diasStr} às ${time}`
}

export default function ConfCron() {
  const { slug } = useParams<{ slug: string }>()
  const [time, setTime] = useState('10:00')
  const [days, setDays] = useState<number[]>([1, 2, 3, 4, 5])
  const [originalExpr, setOriginalExpr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [salvando, setSalvando] = useState(false)
  const [msg, setMsg] = useState<{ tipo: 'ok' | 'erro'; texto: string } | null>(null)

  useEffect(() => {
    setLoading(true)
    setMsg(null)
    api
      .get(`/conf/${slug}/cron`)
      .then((r) => {
        const expr: string = r.data.cron_expression ?? ''
        setOriginalExpr(expr)
        if (expr) {
          const parsed = parseCron(expr)
          setTime(parsed.time)
          setDays(parsed.days)
        }
      })
      .catch(() => setMsg({ tipo: 'erro', texto: 'Erro ao carregar agendamento' }))
      .finally(() => setLoading(false))
  }, [slug])

  const toggleDay = (day: number) =>
    setDays((prev) => (prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]))

  const cronExpr = buildCron(time, days)
  const changed = cronExpr !== originalExpr

  const salvar = async () => {
    setSalvando(true)
    setMsg(null)
    try {
      await api.put(`/conf/${slug}/cron`, { cron_expression: cronExpr })
      setOriginalExpr(cronExpr)
      setMsg({ tipo: 'ok', texto: 'Agendamento atualizado com sucesso' })
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data
        ?.detail
      setMsg({
        tipo: 'erro',
        texto: typeof detail === 'string' ? detail : 'Erro ao salvar agendamento',
      })
    } finally {
      setSalvando(false)
    }
  }

  if (loading) return <p className="text-slate-500 text-sm">Carregando...</p>

  return (
    <div className="max-w-md space-y-6">

      {/* Dias da semana */}
      <div className="space-y-3">
        <p className="text-sm font-medium text-slate-700">Dias da semana</p>
        <div className="flex gap-2">
          {DIAS.map((dia) => {
            const ativo = days.includes(dia.value)
            return (
              <button
                key={dia.value}
                onClick={() => toggleDay(dia.value)}
                className={`w-11 h-11 rounded-full text-xs font-semibold transition-all border-2 ${
                  ativo
                    ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                    : 'bg-white text-slate-500 border-slate-200 hover:border-blue-300 hover:text-blue-500'
                }`}
              >
                {dia.label}
              </button>
            )
          })}
        </div>
        <div className="flex gap-3 text-xs">
          <button
            onClick={() => setDays([1, 2, 3, 4, 5])}
            className="text-blue-600 hover:underline"
          >
            Dias úteis
          </button>
          <span className="text-slate-300">|</span>
          <button
            onClick={() => setDays([0, 1, 2, 3, 4, 5, 6])}
            className="text-blue-600 hover:underline"
          >
            Todos os dias
          </button>
          <span className="text-slate-300">|</span>
          <button onClick={() => setDays([])} className="text-slate-400 hover:underline">
            Limpar
          </button>
        </div>
      </div>

      {/* Horário */}
      <div className="space-y-1.5">
        <p className="text-sm font-medium text-slate-700">Horário</p>
        <input
          type="time"
          value={time}
          onChange={(e) => setTime(e.target.value)}
          className="border border-slate-200 rounded-md px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>

      {/* Preview */}
      <div className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 space-y-2">
        <p className="text-xs text-slate-400 uppercase tracking-wide font-medium">Resumo</p>
        <p className="text-sm text-slate-700">{descricao(time, days)}</p>
        <div className="flex items-center gap-2 pt-1">
          <span className="text-xs text-slate-400">Expressão cron:</span>
          <code className="text-xs font-mono bg-white border border-slate-200 rounded px-2 py-0.5 text-slate-600">
            {cronExpr}
          </code>
        </div>
      </div>

      {/* Feedback */}
      {msg && (
        <p
          className={`text-sm px-3 py-2 rounded-md border ${
            msg.tipo === 'ok'
              ? 'bg-green-50 border-green-200 text-green-700'
              : 'bg-red-50 border-red-200 text-red-600'
          }`}
        >
          {msg.texto}
        </p>
      )}

      <Button onClick={salvar} disabled={salvando || !changed || days.length === 0}>
        {salvando ? 'Salvando...' : 'Salvar agendamento'}
      </Button>
    </div>
  )
}

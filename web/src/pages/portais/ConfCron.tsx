import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import api from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const EXEMPLOS = [
  { label: 'Todo dia às 10h',         expr: '0 10 * * *' },
  { label: 'Dias úteis às 20h',       expr: '0 20 * * 1-5' },
  { label: 'Segunda-feira às 8h',     expr: '0 8 * * 1' },
  { label: 'Todo dia às meia-noite',  expr: '0 0 * * *' },
]

export default function ConfCron() {
  const { slug } = useParams<{ slug: string }>()
  const [expr, setExpr] = useState('')
  const [original, setOriginal] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [salvando, setSalvando] = useState(false)
  const [msg, setMsg] = useState<{ tipo: 'ok' | 'erro'; texto: string } | null>(null)

  useEffect(() => {
    setLoading(true)
    setMsg(null)
    api.get(`/conf/${slug}/cron`)
      .then((r) => {
        const v = r.data.cron_expression ?? ''
        setExpr(v)
        setOriginal(v)
      })
      .catch(() => setMsg({ tipo: 'erro', texto: 'Erro ao carregar cron' }))
      .finally(() => setLoading(false))
  }, [slug])

  const salvar = async () => {
    setSalvando(true)
    setMsg(null)
    try {
      await api.put(`/conf/${slug}/cron`, { cron_expression: expr })
      setOriginal(expr)
      setMsg({ tipo: 'ok', texto: 'Cron atualizado com sucesso' })
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      const texto = typeof detail === 'string' ? detail : 'Erro ao salvar cron'
      setMsg({ tipo: 'erro', texto })
    } finally {
      setSalvando(false)
    }
  }

  if (loading) return <p className="text-slate-500 text-sm">Carregando...</p>

  return (
    <div className="max-w-lg space-y-6">
      <div className="space-y-1.5">
        <Label htmlFor="cron">Expressão Cron</Label>
        <Input
          id="cron"
          value={expr}
          onChange={(e) => setExpr(e.target.value)}
          placeholder="0 10 * * *"
          className="font-mono"
        />
        <p className="text-xs text-slate-500">
          Formato: <span className="font-mono">minuto hora dia-mês mês dia-semana</span>
          &nbsp;(0=Dom … 5=Sex; 1-5=seg-sex)
        </p>
      </div>

      <div className="space-y-1.5">
        <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Exemplos rápidos</p>
        <div className="flex flex-wrap gap-2">
          {EXEMPLOS.map((ex) => (
            <button
              key={ex.expr}
              onClick={() => setExpr(ex.expr)}
              className="text-xs px-2.5 py-1 rounded-full border border-slate-200 hover:border-blue-400 hover:text-blue-600 transition-colors"
            >
              {ex.label} <span className="font-mono text-slate-400 ml-1">{ex.expr}</span>
            </button>
          ))}
        </div>
      </div>

      {msg && (
        <p className={`text-sm px-3 py-2 rounded-md border ${
          msg.tipo === 'ok'
            ? 'bg-green-50 border-green-200 text-green-700'
            : 'bg-red-50 border-red-200 text-red-600'
        }`}>
          {msg.texto}
        </p>
      )}

      <Button onClick={salvar} disabled={salvando || expr === original || !expr.trim()}>
        {salvando ? 'Salvando...' : 'Salvar'}
      </Button>
    </div>
  )
}

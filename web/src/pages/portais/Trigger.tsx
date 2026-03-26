import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { triggerPortal } from '@/api/conf'
import { Button } from '@/components/ui/button'
import { Play } from 'lucide-react'

export default function Trigger() {
  const { slug } = useParams<{ slug: string }>()
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ status: string; message?: string } | null>(null)

  const handleRun = async () => {
    if (!slug) return
    setLoading(true)
    setResult(null)
    try {
      const data = await triggerPortal(slug)
      setResult({ status: 'ok', message: data.message ?? 'Scraper iniciado com sucesso!' })
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setResult({ status: 'erro', message: msg ?? 'Erro ao iniciar o scraper.' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md space-y-4">
      <div className="rounded-lg border border-gray-200 p-5">
        <h3 className="font-medium text-slate-700 mb-1">Execução Manual</h3>
        <p className="text-sm text-slate-500 mb-4">
          Dispara o scraper imediatamente, fora do agendamento automático.
        </p>
        <Button onClick={handleRun} disabled={loading} className="flex items-center gap-2">
          <Play size={15} />
          {loading ? 'Iniciando...' : 'Executar Agora'}
        </Button>
      </div>

      {result && (
        <div className={`rounded-lg border px-4 py-3 text-sm ${
          result.status === 'ok'
            ? 'bg-green-50 border-green-200 text-green-700'
            : 'bg-red-50 border-red-200 text-red-700'
        }`}>
          {result.message}
        </div>
      )}
    </div>
  )
}

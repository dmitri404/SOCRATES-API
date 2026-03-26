import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getConfGeral, putConfGeral } from '@/api/conf'
import { useAuthStore } from '@/store/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

export default function ConfGeral() {
  const { slug } = useParams<{ slug: string }>()
  const { user } = useAuthStore()
  const canEdit = user?.portais.find((p) => p.slug === slug)?.pode_editar ?? false

  const [urlBase, setUrlBase] = useState('')
  const [modeLimpar, setModeLimpar] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    if (!slug) return
    getConfGeral(slug)
      .then((d) => { setUrlBase(d.url_base ?? ''); setModeLimpar(d.modo_limpar ?? false) })
      .finally(() => setLoading(false))
  }, [slug])

  const handleSave = async () => {
    if (!slug) return
    setSaving(true)
    setMsg('')
    try {
      await putConfGeral(slug, { url_base: urlBase, modo_limpar: modeLimpar })
      setMsg('Salvo com sucesso!')
    } catch {
      setMsg('Erro ao salvar.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="text-sm text-slate-500">Carregando...</p>

  return (
    <div className="max-w-md space-y-5">
      <div className="space-y-1.5">
        <Label>URL Base</Label>
        <Input
          value={urlBase}
          onChange={(e) => setUrlBase(e.target.value)}
          disabled={!canEdit}
          placeholder="https://..."
        />
      </div>

      <div className="flex items-center justify-between rounded-lg border border-gray-200 p-4">
        <div>
          <p className="text-sm font-medium text-slate-700">Modo Limpar</p>
          <p className="text-xs text-slate-500">Força reprocessamento de todos os exercícios</p>
        </div>
        <Switch checked={modeLimpar} onCheckedChange={setModeLimpar} disabled={!canEdit} />
      </div>

      {canEdit && (
        <div className="flex items-center gap-3">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? 'Salvando...' : 'Salvar'}
          </Button>
          {msg && <span className="text-sm text-slate-500">{msg}</span>}
        </div>
      )}
    </div>
  )
}

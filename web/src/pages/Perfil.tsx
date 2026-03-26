import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { alterarSenha } from '@/api/auth'
import { useAuthStore } from '@/store/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export default function Perfil() {
  const { user, setUser } = useAuthStore()
  const [searchParams] = useSearchParams()
  const trocarSenha = searchParams.get('trocar-senha') === '1'

  const [atual, setAtual] = useState('')
  const [nova, setNova] = useState('')
  const [confirma, setConfirma] = useState('')
  const [msg, setMsg] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (nova !== confirma) { setMsg('As senhas não coincidem.'); return }
    setLoading(true)
    setMsg('')
    try {
      await alterarSenha(atual, nova)
      if (user) setUser({ ...user, senha_temp: false })
      setMsg('Senha alterada com sucesso!')
      setAtual(''); setNova(''); setConfirma('')
    } catch (err: unknown) {
      const m = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setMsg(m ?? 'Erro ao alterar senha.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-md">
      <h2 className="text-2xl font-bold text-slate-800 mb-6">Perfil</h2>

      {trocarSenha && (
        <div className="mb-5 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-700">
          Você está usando uma senha temporária. Por favor, defina uma nova senha.
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div>
          <p className="text-xs text-slate-500">Nome</p>
          <p className="text-sm font-medium text-slate-700">{user?.nome}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">E-mail</p>
          <p className="text-sm font-medium text-slate-700">{user?.email}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Perfil</p>
          <p className="text-sm font-medium text-slate-700 capitalize">{user?.role}</p>
        </div>
      </div>

      <div className="mt-6 bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="font-medium text-slate-700 mb-4">Alterar Senha</h3>
        <form onSubmit={handleSave} className="space-y-3">
          <div className="space-y-1.5">
            <Label>Senha Atual</Label>
            <Input type="password" value={atual} onChange={(e) => setAtual(e.target.value)} required />
          </div>
          <div className="space-y-1.5">
            <Label>Nova Senha</Label>
            <Input type="password" value={nova} onChange={(e) => setNova(e.target.value)} required />
          </div>
          <div className="space-y-1.5">
            <Label>Confirmar Nova Senha</Label>
            <Input type="password" value={confirma} onChange={(e) => setConfirma(e.target.value)} required />
          </div>
          {msg && (
            <p className={`text-sm ${msg.includes('sucesso') ? 'text-green-600' : 'text-red-600'}`}>{msg}</p>
          )}
          <Button type="submit" disabled={loading}>
            {loading ? 'Salvando...' : 'Alterar Senha'}
          </Button>
        </form>
      </div>
    </div>
  )
}

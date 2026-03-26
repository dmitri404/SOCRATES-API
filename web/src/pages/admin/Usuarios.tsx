import { useEffect, useState, useCallback } from 'react'
import { getUsuarios, getPortais, postUsuario, patchUsuario, resetarSenha, putPortais } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface Portal { slug: string; nome: string; pode_editar: boolean }
interface Usuario {
  id: string
  usuario: string
  nome: string
  email: string
  role: 'admin' | 'supervisor' | 'usuario'
  ativo: boolean
  senha_temp: boolean
  ultimo_login: string | null
  portais: Portal[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const ROLE_LABEL: Record<string, string> = {
  admin: 'Admin',
  supervisor: 'Supervisor',
  usuario: 'Usuário',
}

const ROLE_COLOR: Record<string, string> = {
  admin:      'bg-blue-100 text-blue-700',
  supervisor: 'bg-purple-100 text-purple-700',
  usuario:    'bg-slate-100 text-slate-600',
}

function fmtDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function apiErr(err: unknown, fallback = 'Erro') {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

// ── Modal base ────────────────────────────────────────────────────────────────

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-slate-800">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">&times;</button>
        </div>
        <div className="overflow-y-auto px-6 py-4 space-y-4 flex-1">{children}</div>
      </div>
    </div>
  )
}

// ── Modal: Criar / Editar usuário ─────────────────────────────────────────────

function ModalUsuario({
  usuario,
  onClose,
  onSaved,
}: {
  usuario: Usuario | null
  onClose: () => void
  onSaved: () => void
}) {
  const editando = !!usuario
  const [form, setForm] = useState({
    usuario: usuario?.usuario ?? '',
    nome:    usuario?.nome    ?? '',
    email:   usuario?.email   ?? '',
    role:    usuario?.role    ?? 'usuario',
    senha:   '',
  })
  const [loading, setLoading] = useState(false)
  const [erro, setErro] = useState('')

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const salvar = async () => {
    setLoading(true)
    setErro('')
    try {
      if (editando) {
        await patchUsuario(usuario!.id, { nome: form.nome, email: form.email, role: form.role })
      } else {
        if (!form.senha) { setErro('Informe a senha inicial'); setLoading(false); return }
        await postUsuario(form)
      }
      onSaved()
      onClose()
    } catch (err) {
      setErro(apiErr(err, 'Erro ao salvar usuário'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal title={editando ? 'Editar usuário' : 'Novo usuário'} onClose={onClose}>
      <div className="space-y-1.5">
        <Label>Usuário (login)</Label>
        <Input value={form.usuario} onChange={set('usuario')} disabled={editando} placeholder="nome.sobrenome" />
      </div>
      <div className="space-y-1.5">
        <Label>Nome completo</Label>
        <Input value={form.nome} onChange={set('nome')} placeholder="João da Silva" />
      </div>
      <div className="space-y-1.5">
        <Label>E-mail</Label>
        <Input type="email" value={form.email} onChange={set('email')} placeholder="joao@exemplo.com" />
      </div>
      <div className="space-y-1.5">
        <Label>Perfil</Label>
        <select
          value={form.role}
          onChange={set('role')}
          className="w-full border border-slate-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="usuario">Usuário</option>
          <option value="supervisor">Supervisor</option>
          <option value="admin">Admin</option>
        </select>
      </div>
      {!editando && (
        <div className="space-y-1.5">
          <Label>Senha inicial</Label>
          <Input type="password" value={form.senha} onChange={set('senha')} placeholder="••••••••" />
          <p className="text-xs text-slate-400">O usuário deverá trocar ao primeiro acesso.</p>
        </div>
      )}
      {erro && <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">{erro}</p>}
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" onClick={onClose} disabled={loading}>Cancelar</Button>
        <Button onClick={salvar} disabled={loading}>{loading ? 'Salvando...' : 'Salvar'}</Button>
      </div>
    </Modal>
  )
}

// ── Modal: Atribuir portais ───────────────────────────────────────────────────

function ModalPortais({
  usuario,
  todosPortais,
  onClose,
  onSaved,
}: {
  usuario: Usuario
  todosPortais: { slug: string; nome: string }[]
  onClose: () => void
  onSaved: () => void
}) {
  const [selecionados, setSelecionados] = useState<Record<string, boolean>>(
    Object.fromEntries(usuario.portais.map((p) => [p.slug, true]))
  )
  const [podeEditar, setPodeEditar] = useState<Record<string, boolean>>(
    Object.fromEntries(usuario.portais.map((p) => [p.slug, p.pode_editar]))
  )
  const [loading, setLoading] = useState(false)
  const [erro, setErro] = useState('')

  const togglePortal = (slug: string) =>
    setSelecionados((s) => ({ ...s, [slug]: !s[slug] }))

  const toggleEditar = (slug: string) =>
    setPodeEditar((s) => ({ ...s, [slug]: !s[slug] }))

  const salvar = async () => {
    setLoading(true)
    setErro('')
    const portais = todosPortais
      .filter((p) => selecionados[p.slug])
      .map((p) => ({ slug: p.slug, pode_editar: podeEditar[p.slug] ?? true }))
    try {
      await putPortais(usuario.id, portais)
      onSaved()
      onClose()
    } catch (err) {
      setErro(apiErr(err, 'Erro ao salvar portais'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal title={`Portais — ${usuario.nome}`} onClose={onClose}>
      <div className="space-y-2">
        {todosPortais.map((p) => (
          <div key={p.slug} className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={!!selecionados[p.slug]}
                onChange={() => togglePortal(p.slug)}
                className="rounded"
              />
              <span className="text-sm text-slate-700">{p.nome}</span>
            </label>
            {selecionados[p.slug] && (
              <label className="flex items-center gap-1.5 text-xs text-slate-500 cursor-pointer">
                <input
                  type="checkbox"
                  checked={podeEditar[p.slug] ?? true}
                  onChange={() => toggleEditar(p.slug)}
                  className="rounded"
                />
                Pode editar
              </label>
            )}
          </div>
        ))}
      </div>
      {erro && <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">{erro}</p>}
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" onClick={onClose} disabled={loading}>Cancelar</Button>
        <Button onClick={salvar} disabled={loading}>{loading ? 'Salvando...' : 'Salvar'}</Button>
      </div>
    </Modal>
  )
}

// ── Modal: Senha resetada ─────────────────────────────────────────────────────

function ModalSenhaResetada({ senha, nome, onClose }: { senha: string; nome: string; onClose: () => void }) {
  return (
    <Modal title="Senha resetada" onClose={onClose}>
      <p className="text-sm text-slate-600">
        A senha temporária de <strong>{nome}</strong> foi redefinida. Repasse ao usuário:
      </p>
      <div className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-center">
        <code className="text-lg font-mono font-bold tracking-widest text-slate-800">{senha}</code>
      </div>
      <p className="text-xs text-slate-400">O usuário deverá trocar a senha no próximo acesso.</p>
      <div className="flex justify-end pt-2">
        <Button onClick={onClose}>Fechar</Button>
      </div>
    </Modal>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function Usuarios() {
  const [usuarios, setUsuarios] = useState<Usuario[]>([])
  const [portais, setPortais]   = useState<{ slug: string; nome: string }[]>([])
  const [loading, setLoading]   = useState(true)

  const [modal, setModal] = useState<
    | { tipo: 'criar' }
    | { tipo: 'editar';  usuario: Usuario }
    | { tipo: 'portais'; usuario: Usuario }
    | { tipo: 'senha';   nome: string; senha: string }
    | null
  >(null)

  const carregar = useCallback(async () => {
    setLoading(true)
    try {
      const [u, p] = await Promise.all([getUsuarios(), getPortais()])
      setUsuarios(u)
      setPortais(p)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { carregar() }, [carregar])

  const toggleAtivo = async (u: Usuario) => {
    await patchUsuario(u.id, { ativo: !u.ativo })
    carregar()
  }

  const handleReset = async (u: Usuario) => {
    const res = await resetarSenha(u.id)
    setModal({ tipo: 'senha', nome: u.nome, senha: res.senha_temp })
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-slate-800">Usuários</h2>
        <Button onClick={() => setModal({ tipo: 'criar' })}>+ Novo usuário</Button>
      </div>

      {loading ? (
        <p className="text-slate-500 text-sm">Carregando...</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 uppercase text-xs tracking-wide">
              <tr>
                <th className="px-4 py-3 text-left">Nome</th>
                <th className="px-4 py-3 text-left">Usuário</th>
                <th className="px-4 py-3 text-left">Perfil</th>
                <th className="px-4 py-3 text-left">Portais</th>
                <th className="px-4 py-3 text-left">Último acesso</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {usuarios.map((u) => (
                <tr key={u.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-slate-800">
                    {u.nome}
                    {u.senha_temp && (
                      <span className="ml-2 text-xs bg-yellow-100 text-yellow-700 rounded-full px-1.5 py-0.5">temp</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500 font-mono">{u.usuario}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium rounded-full px-2.5 py-1 ${ROLE_COLOR[u.role]}`}>
                      {ROLE_LABEL[u.role]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-500 max-w-48">
                    {u.portais.length === 0
                      ? <span className="text-slate-300">—</span>
                      : u.portais.map((p) => p.nome.replace('Portal ', '')).join(', ')}
                  </td>
                  <td className="px-4 py-3 text-slate-400 whitespace-nowrap">{fmtDate(u.ultimo_login)}</td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => toggleAtivo(u)}
                      className={`text-xs font-medium rounded-full px-2.5 py-1 transition-colors ${
                        u.ativo
                          ? 'bg-green-100 text-green-700 hover:bg-green-200'
                          : 'bg-red-100 text-red-600 hover:bg-red-200'
                      }`}
                    >
                      {u.ativo ? 'Ativo' : 'Inativo'}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      <button
                        onClick={() => setModal({ tipo: 'editar', usuario: u })}
                        className="text-xs px-2.5 py-1 rounded border border-slate-200 hover:border-blue-300 hover:text-blue-600 transition-colors"
                      >
                        Editar
                      </button>
                      <button
                        onClick={() => setModal({ tipo: 'portais', usuario: u })}
                        className="text-xs px-2.5 py-1 rounded border border-slate-200 hover:border-blue-300 hover:text-blue-600 transition-colors"
                      >
                        Portais
                      </button>
                      <button
                        onClick={() => handleReset(u)}
                        className="text-xs px-2.5 py-1 rounded border border-slate-200 hover:border-orange-300 hover:text-orange-600 transition-colors"
                      >
                        Resetar
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modal?.tipo === 'criar' && (
        <ModalUsuario usuario={null} onClose={() => setModal(null)} onSaved={carregar} />
      )}
      {modal?.tipo === 'editar' && (
        <ModalUsuario usuario={modal.usuario} onClose={() => setModal(null)} onSaved={carregar} />
      )}
      {modal?.tipo === 'portais' && (
        <ModalPortais
          usuario={modal.usuario}
          todosPortais={portais}
          onClose={() => setModal(null)}
          onSaved={carregar}
        />
      )}
      {modal?.tipo === 'senha' && (
        <ModalSenhaResetada senha={modal.senha} nome={modal.nome} onClose={() => setModal(null)} />
      )}
    </div>
  )
}

import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { getCredores, postCredor, deleteCredor, toggleCredor } from '@/api/conf'
import { useAuthStore } from '@/store/auth'
import ConfTable from './ConfTable'

export default function ConfCredores() {
  const { slug } = useParams<{ slug: string }>()
  const { user } = useAuthStore()
  const canEdit = user?.portais.find((p) => p.slug === slug)?.pode_editar ?? false

  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    if (!slug) return
    getCredores(slug).then(setRows).finally(() => setLoading(false))
  }, [slug])

  useEffect(() => { load() }, [load])

  if (loading) return <p className="text-sm text-slate-500">Carregando...</p>

  return (
    <ConfTable
      rows={rows}
      columns={[
        { key: 'cpf', label: 'CPF / CNPJ', placeholder: '00.000.000/0000-00' },
        { key: 'nome', label: 'Nome', placeholder: 'Nome do credor' },
      ]}
      canEdit={canEdit}
      onAdd={async (v) => { await postCredor(slug!, v); load() }}
      onDelete={async (id) => { await deleteCredor(slug!, id); load() }}
      onToggle={async (id) => { await toggleCredor(slug!, id); load() }}
    />
  )
}

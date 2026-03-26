import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { getEmails, postEmail, deleteEmail, toggleEmail } from '@/api/conf'
import { useAuthStore } from '@/store/auth'
import ConfTable from './ConfTable'

export default function ConfEmails() {
  const { slug } = useParams<{ slug: string }>()
  const { user } = useAuthStore()
  const canEdit = user?.portais.find((p) => p.slug === slug)?.pode_editar ?? false

  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    if (!slug) return
    getEmails(slug).then(setRows).finally(() => setLoading(false))
  }, [slug])

  useEffect(() => { load() }, [load])

  if (loading) return <p className="text-sm text-slate-500">Carregando...</p>

  return (
    <ConfTable
      rows={rows}
      columns={[
        { key: 'email', label: 'E-mail', placeholder: 'email@exemplo.com' },
        { key: 'nome', label: 'Nome', placeholder: 'Nome' },
      ]}
      canEdit={canEdit}
      onAdd={async (v) => { await postEmail(slug!, v); load() }}
      onDelete={async (id) => { await deleteEmail(slug!, id); load() }}
      onToggle={async (id) => { await toggleEmail(slug!, id); load() }}
    />
  )
}

import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { getExercicios, postExercicio, deleteExercicio, toggleExercicio } from '@/api/conf'
import { useAuthStore } from '@/store/auth'
import ConfTable from './ConfTable'

export default function ConfExercicios() {
  const { slug } = useParams<{ slug: string }>()
  const { user } = useAuthStore()
  const canEdit = user?.portais.find((p) => p.slug === slug)?.pode_editar ?? false

  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    if (!slug) return
    getExercicios(slug).then(setRows).finally(() => setLoading(false))
  }, [slug])

  useEffect(() => { load() }, [load])

  if (loading) return <p className="text-sm text-slate-500">Carregando...</p>

  return (
    <ConfTable
      rows={rows}
      columns={[
        { key: 'exercicio', label: 'Exercício', placeholder: '2025' },
      ]}
      canEdit={canEdit}
      onAdd={async (v) => { await postExercicio(slug!, v); load() }}
      onDelete={async (id) => { await deleteExercicio(slug!, id); load() }}
      onToggle={async (id) => { await toggleExercicio(slug!, id); load() }}
    />
  )
}

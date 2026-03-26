import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Trash2, Plus } from 'lucide-react'

interface Row {
  id: number
  ativo: boolean
  [key: string]: unknown
}

interface Column {
  key: string
  label: string
  placeholder?: string
}

interface Props {
  rows: Row[]
  columns: Column[]
  canEdit: boolean
  onAdd: (values: Record<string, string>) => Promise<void>
  onDelete: (id: number) => Promise<void>
  onToggle: (id: number) => Promise<void>
}

export default function ConfTable({ rows, columns, canEdit, onAdd, onDelete, onToggle }: Props) {
  const [form, setForm] = useState<Record<string, string>>({})
  const [adding, setAdding] = useState(false)
  const [loadingId, setLoadingId] = useState<number | null>(null)

  const handleAdd = async () => {
    setAdding(true)
    try {
      await onAdd(form)
      setForm({})
    } finally {
      setAdding(false)
    }
  }

  const handleToggle = async (id: number) => {
    setLoadingId(id)
    try { await onToggle(id) } finally { setLoadingId(null) }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Remover este item?')) return
    setLoadingId(id)
    try { await onDelete(id) } finally { setLoadingId(null) }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {columns.map((c) => (
                <th key={c.key} className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                  {c.label}
                </th>
              ))}
              <th className="px-4 py-3 text-center text-xs font-medium text-slate-500 uppercase tracking-wider w-20">Ativo</th>
              {canEdit && <th className="w-12" />}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.length === 0 && (
              <tr>
                <td colSpan={columns.length + 2} className="px-4 py-6 text-center text-slate-400 text-sm">
                  Nenhum registro
                </td>
              </tr>
            )}
            {rows.map((row) => (
              <tr key={row.id} className="hover:bg-gray-50">
                {columns.map((c) => (
                  <td key={c.key} className="px-4 py-3 text-slate-700">{String(row[c.key] ?? '')}</td>
                ))}
                <td className="px-4 py-3 text-center">
                  <Switch
                    checked={row.ativo}
                    onCheckedChange={() => handleToggle(row.id)}
                    disabled={!canEdit || loadingId === row.id}
                  />
                </td>
                {canEdit && (
                  <td className="px-2 py-3 text-center">
                    <button
                      onClick={() => handleDelete(row.id)}
                      disabled={loadingId === row.id}
                      className="text-slate-400 hover:text-red-500 transition-colors"
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {canEdit && (
        <div className="flex gap-2 items-end">
          {columns.map((c) => (
            <div key={c.key} className="flex-1">
              <Input
                value={form[c.key] ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, [c.key]: e.target.value }))}
                placeholder={c.placeholder ?? c.label}
              />
            </div>
          ))}
          <Button size="sm" onClick={handleAdd} disabled={adding} className="flex items-center gap-1 shrink-0">
            <Plus size={14} />
            Adicionar
          </Button>
        </div>
      )}
    </div>
  )
}

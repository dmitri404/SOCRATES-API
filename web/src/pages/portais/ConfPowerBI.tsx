import { useParams } from 'react-router-dom'

const EMBEDS: Record<string, string> = {
  municipal: 'https://app.powerbi.com/view?r=eyJrIjoiNzkzNzY4N2UtOWVkZC00MmYyLTk5MTEtZmNiY2MxMjczZjhjIiwidCI6IjNmMDdmNzQyLTQyODEtNGNlMC05NTI0LTE1NDQ2YzUxYWQ3NiJ9',
}

export default function ConfPowerBI() {
  const { slug } = useParams<{ slug: string }>()
  const src = slug ? EMBEDS[slug] : undefined

  if (!src) return <p className="text-slate-400 text-sm">Nenhum painel configurado para este portal.</p>

  return (
    <div className="w-full" style={{ aspectRatio: '16/9' }}>
      <iframe
        title="Power BI"
        src={src}
        className="w-full h-full rounded-xl border border-gray-200"
        frameBorder={0}
        allowFullScreen
      />
    </div>
  )
}

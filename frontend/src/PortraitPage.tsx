import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Result, post, request } from './api'
import { PixelAvatar } from './pixel/Avatar'
import { usePersona } from './persona'
import { PageTitle, SKILL_COLOR, Spinner } from './ui'

export default function PortraitPage() {
  const { persona } = usePersona()
  const [portrait, setPortrait] = useState<Result | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { request<Result | null>('/portrait').then(setPortrait).catch(e => setError(e.message)).finally(() => setLoaded(true)) }, [])
  const generate = async () => { setBusy(true); setError(''); try { setPortrait(await post<Result>('/portrait/generate')) } catch (e) { setError((e as Error).message) } finally { setBusy(false) } }
  return <>
    <PageTitle eyebrow="Learning Coordinator" title="Your learning portrait" subtitle="A snapshot of where you start and where you're heading." />
    {error && <div className="panel panel-hot mb-5 p-5 font-read text-rose">{error}</div>}
    {!loaded ? <Spinner /> : !portrait ? <div className="panel p-7"><p className="font-read">Your account has a profile, but no portrait yet.</p><button onClick={generate} disabled={busy} className="btn-primary mt-4">Create starting portrait<ArrowRight size={16} /></button></div>
      : portrait.state !== 'RELEASED' ? <div className="panel panel-sun p-7 font-read text-sun">Your portrait is held for quality or instructor review. It will appear after release.</div>
        : <div className="space-y-5">
          <div className="panel panel-hot grid items-center gap-6 p-7 md:grid-cols-[auto_1fr]"><PixelAvatar persona={persona} mood="happy" size={120} />
            <div><span className="pill text-cyan">{portrait.source_mode === 'REAL' ? 'Cloud AI portrait' : 'Built-in coordinator portrait'} · quality checked</span><h2 className="heading mt-4 text-2xl">Starting point</h2><p className="mt-3 font-read">{portrait.payload?.summary}</p><p className="mt-3 font-read text-sm text-mist">{portrait.payload?.starting_point}</p></div></div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="panel p-6"><h3 className="section-title">Goal and rhythm</h3><p className="mt-3 font-read">{portrait.payload?.goal}</p><p className="mt-3 font-read text-mist">{portrait.payload?.study_rhythm}</p></div>
            <div className="panel p-6"><h3 className="section-title">Focus areas</h3><div className="mt-4 flex flex-wrap gap-2">{(portrait.payload?.focus_areas || []).map((skill: string) => <Link to={`/practice/${skill}`} key={skill} className="pill" style={{ color: SKILL_COLOR[skill] }}>{skill}</Link>)}</div></div>
          </div>
          <div className="panel p-6"><h3 className="section-title">Recommended first steps</h3><ol className="mt-3 space-y-2 font-read">{(portrait.payload?.next_steps || []).map((step: string, index: number) => <li key={index}><span className="mr-2 font-terminal text-xl text-magenta">{index + 1}.</span>{step}</li>)}</ol></div>
          <button onClick={generate} disabled={busy} className="btn-secondary">Refresh from current profile</button>
          <p className="font-read text-sm text-fog">The portrait reflects self-reported goals. Verified results appear in Performance and the knowledge graph.</p>
        </div>}
  </>
}

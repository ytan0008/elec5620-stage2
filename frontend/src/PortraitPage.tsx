import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, UserRound } from 'lucide-react'
import { Result, post, request } from './api'

export default function PortraitPage(){
  const [portrait,setPortrait]=useState<Result|null>(null)
  const [loaded,setLoaded]=useState(false)
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  useEffect(()=>{request<Result|null>('/portrait').then(setPortrait).catch(e=>setError(e.message)).finally(()=>setLoaded(true))},[])
  const generate=async()=>{setBusy(true);setError('');try{setPortrait(await post<Result>('/portrait/generate'))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  return <div className="space-y-6"><div className="flex items-center gap-3"><span className="rounded-2xl bg-mint p-3 text-teal"><UserRound/></span><div><span className="eyebrow">Learning Coordinator</span><h1 className="heading text-3xl">Your learning portrait</h1></div></div>
    {error&&<div className="card p-5 text-red-700">{error}</div>}{!loaded?<div className="card p-6">Loading portrait…</div>:!portrait?<div className="card p-7"><p>Your account has a profile, but no portrait has been created yet.</p><button onClick={generate} disabled={busy} className="btn-primary mt-4">Create starting portrait<ArrowRight size={17}/></button></div>:portrait.state!=='RELEASED'?<div className="card border-amber-200 bg-amber-50 p-7 text-amber-800">Your portrait is held for quality or instructor review. It will appear here after release.</div>:<><div className="card p-7"><span className="pill bg-mint text-teal">{portrait.source_mode==='DEMO'?'Deterministic demo portrait':'AI-generated, quality-checked portrait'}</span><h2 className="heading mt-4 text-2xl">Starting point</h2><p className="mt-3 text-slate-700">{portrait.payload?.summary}</p><p className="mt-4 text-sm text-slate-500">{portrait.payload?.starting_point}</p></div><div className="grid gap-4 md:grid-cols-2"><div className="card p-6"><h3 className="section-title">Goal and rhythm</h3><p className="mt-3 text-slate-700">{portrait.payload?.goal}</p><p className="mt-3 text-slate-700">{portrait.payload?.study_rhythm}</p></div><div className="card p-6"><h3 className="section-title">Focus areas</h3><div className="mt-4 flex flex-wrap gap-2">{(portrait.payload?.focus_areas||[]).map((skill:string)=><Link to={`/practice/${skill}`} key={skill} className="pill bg-mint text-teal">{skill}</Link>)}</div></div></div><div className="card p-6"><h3 className="section-title">Recommended first steps</h3><ol className="mt-3 list-inside list-decimal space-y-2 text-slate-700">{(portrait.payload?.next_steps||[]).map((step:string,index:number)=><li key={index}>{step}</li>)}</ol></div><button onClick={generate} disabled={busy} className="btn-secondary">Refresh from current profile</button><p className="text-sm text-slate-500">This portrait reflects self-reported goals. Verified practice results appear separately in Performance and the knowledge graph; confidence is not a calibrated probability.</p></>}
  </div>
}

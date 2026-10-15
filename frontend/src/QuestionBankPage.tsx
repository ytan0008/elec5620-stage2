import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, ExternalLink, Sparkles } from 'lucide-react'
import { Practice, Profile, post, request } from './api'

type Question={id:number;exam:string;skill:string;task_type:string;title:string;prompt:string|null;topic:string;source_kind:string;source_url:string|null;available:boolean;verification_state:string}
type Notify=(message:string,kind?:'success'|'error')=>void
const skills=['all','listening','reading','writing','speaking']

export default function QuestionBankPage({notify}:{notify:Notify}){
  const navigate=useNavigate()
  const [items,setItems]=useState<Question[]>([])
  const [profile,setProfile]=useState<Profile|null>(null)
  const [skill,setSkill]=useState('all')
  const [topic,setTopic]=useState('technology and education')
  const [generateSkill,setGenerateSkill]=useState<'writing'|'speaking'>('writing')
  const [busy,setBusy]=useState(false)
  useEffect(()=>{request<Question[]>('/questions').then(setItems).catch(e=>notify(e.message,'error'));request<Profile>('/profile').then(setProfile).catch(()=>{})},[])
  const generate=async()=>{setBusy(true);try{const item=await post<Question>('/questions/generate',{skill:generateSkill,topic});setItems(previous=>[...previous,item]);notify(item.available?'Original practice task generated':'Generated task held for quality review')}catch(e){notify((e as Error).message,'error')}finally{setBusy(false)}}
  const start=async(item:Question)=>{setBusy(true);try{const practice=await post<Practice>(`/practice/${item.skill}?question_id=${item.id}`);navigate(`/practice/${item.skill}?session=${practice.id}`)}catch(e){notify((e as Error).message,'error')}finally{setBusy(false)}}
  return <div className="space-y-6">
    <div><span className="eyebrow">IELTS preparation</span><h1 className="heading mt-1 text-3xl">Question bank</h1><p className="mt-2 max-w-3xl text-slate-600">Browse original IELTS-style tasks and links to public official samples. Official questions open on the publisher's site; generated tasks are clearly labelled and quality checked.</p></div>
    {profile?.exam!=='IELTS'&&<div className="card border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">This question bank is for IELTS. <Link to="/profile" className="font-bold underline">Switch your profile to IELTS</Link> to practise these tasks.</div>}
    <div className="card p-6"><div className="flex items-center gap-2"><Sparkles className="text-teal"/><h2 className="section-title">Generate an original task</h2></div><p className="mt-2 text-sm text-slate-500">Writing Task 2 or Speaking Part 2. Demo mode uses a deterministic template; real AI mode uses the configured model.</p><div className="mt-4 grid gap-3 sm:grid-cols-[160px_1fr_auto]"><select aria-label="Generated task skill" className="input" value={generateSkill} onChange={e=>setGenerateSkill(e.target.value as 'writing'|'speaking')}><option value="writing">Writing</option><option value="speaking">Speaking</option></select><input aria-label="Task topic" className="input" value={topic} maxLength={80} onChange={e=>setTopic(e.target.value)} placeholder="Topic, e.g. public transport"/><button onClick={generate} disabled={busy||topic.trim().length<3||profile?.exam!=='IELTS'} className="btn-primary">Generate<Sparkles size={17}/></button></div></div>
    <div className="flex flex-wrap gap-2">{skills.map(item=><button key={item} onClick={()=>setSkill(item)} className={`pill border ${skill===item?'border-teal bg-mint text-teal':'border-slate-200 bg-white text-slate-600'}`}>{item==='all'?'All skills':item.charAt(0).toUpperCase()+item.slice(1)}</button>)}</div>
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{items.filter(item=>skill==='all'||item.skill===skill).map(item=><article key={item.id} className="card flex flex-col p-6"><div className="flex flex-wrap gap-2"><span className="pill bg-slate-100 text-slate-600">{item.skill}</span><span className={`pill ${item.source_kind==='OFFICIAL_LINK'?'bg-blue-50 text-blue-700':item.source_kind==='ORIGINAL'?'bg-mint text-teal':'bg-violet-50 text-violet-700'}`}>{item.source_kind==='OFFICIAL_LINK'?'Official sample link':item.source_kind==='ORIGINAL'?'Original practice':item.source_kind==='DEMO_GENERATED'?'Demo generated':'AI generated'}</span></div><h2 className="heading mt-4 text-xl">{item.title}</h2><p className="mt-1 text-xs font-semibold uppercase tracking-wide text-slate-400">{item.task_type} · {item.topic}</p><p className="mt-4 flex-1 text-sm leading-relaxed text-slate-600">{item.prompt?item.prompt:item.source_kind==='OFFICIAL_LINK'?'Open the official publisher page to see the authentic sample task.':'This task is awaiting quality review.'}</p><div className="mt-5">{item.source_url?<a href={item.source_url} target="_blank" rel="noopener noreferrer" className="btn-secondary w-full">Open official source<ExternalLink size={16}/></a>:<button onClick={()=>start(item)} disabled={busy||!item.available||profile?.exam!=='IELTS'} className="btn-primary w-full">{item.available?'Start practice':'Held for review'}<ArrowRight size={16}/></button>}</div></article>)}</div>
  </div>
}

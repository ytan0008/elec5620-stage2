import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Bot, CheckCircle2, Send } from 'lucide-react'
import { Profile, Result, post, request } from './api'

type State = {draft:Partial<Profile>;messages:{role:string;text:string}[];ready:boolean;completed:boolean;next_field:string|null;assistant_message:string;mode:string}
type Notify = (message:string,kind?:'success'|'error')=>void

const choices:Record<string,string[]> = {
  exam:['IELTS','TOEFL'], proficiency:['beginner','intermediate','advanced'],
  target_score:['6.0','6.5','7.0','7.5'], weekly_hours:['4','6','8','10'],
  priority_skills:['writing and speaking','reading and listening','all four skills'],
}

export default function OnboardingPage({onComplete,notify}:{onComplete:()=>void;notify:Notify}){
  const [state,setState]=useState<State|null>(null)
  const [answer,setAnswer]=useState('')
  const [busy,setBusy]=useState(false)
  const [portrait,setPortrait]=useState<Result|null>(null)
  useEffect(()=>{request<State>('/onboarding').then(data=>{setState(data);if(data.completed)onComplete()}).catch(error=>notify(error.message,'error'))},[])
  const send=async(value:string)=>{
    if(!value.trim()||busy)return
    setBusy(true)
    try{setState(await post<State>('/onboarding/message',{message:value.trim()}));setAnswer('')}
    catch(error){notify((error as Error).message,'error')}
    finally{setBusy(false)}
  }
  const confirm=async()=>{
    setBusy(true)
    try{const response=await post<{profile:Profile;portrait:Result}>('/onboarding/confirm');setPortrait(response.portrait);onComplete();notify('Your profile is ready')}
    catch(error){notify((error as Error).message,'error')}
    finally{setBusy(false)}
  }
  if(!state)return <div className="card p-8">Loading your coordinator…</div>
  const transcript=state.messages.length?state.messages:[{role:'assistant',text:state.assistant_message}]
  return <div className="mx-auto max-w-6xl space-y-6">
    <div className="rounded-3xl bg-navy p-7 text-white md:p-9">
      <div className="flex items-center gap-3"><span className="rounded-2xl bg-mint p-3 text-teal"><Bot/></span><div><p className="text-xs font-bold uppercase tracking-widest text-mint">Learning Coordinator · {state.mode === 'DEMO'?'deterministic demo':'real AI'}</p><h1 className="font-display text-3xl font-bold">Let's build your learning profile</h1></div></div>
      <p className="mt-4 max-w-2xl text-slate-300">Tell me about your exam goal. I will ask one detail at a time, then prepare a starting portrait. Your answers are saved so you can return later.</p>
    </div>
    <div className="grid gap-6 lg:grid-cols-[1.25fr_.75fr]">
      <div className="card flex min-h-[520px] flex-col p-5 md:p-7">
        <div className="flex-1 space-y-4 overflow-auto" aria-label="Profile conversation">
          {transcript.map((message,index)=><div key={index} className={`flex ${message.role==='learner'?'justify-end':'justify-start'}`}><div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${message.role==='learner'?'bg-teal text-white':'bg-slate-100 text-ink'}`}>{message.text}</div></div>)}
        </div>
        {!state.completed&&!state.ready&&<div className="mt-6 border-t border-slate-100 pt-5">
          {choices[state.next_field||'']&&<div className="mb-3 flex flex-wrap gap-2">{choices[state.next_field||''].map(choice=><button key={choice} onClick={()=>send(choice)} disabled={busy} className="pill border border-teal/30 bg-mint text-teal hover:bg-teal hover:text-white">{choice}</button>)}</div>}
          <form onSubmit={event=>{event.preventDefault();send(answer)}} className="flex gap-2"><input aria-label="Your reply" className="input" value={answer} onChange={event=>setAnswer(event.target.value)} placeholder={state.next_field==='exam_date'?'YYYY-MM-DD':'Type your answer…'}/><button disabled={busy||!answer.trim()} className="btn-primary" aria-label="Send reply"><Send size={18}/></button></form>
        </div>}
        {state.ready&&!state.completed&&!portrait&&<button onClick={confirm} disabled={busy} className="btn-primary mt-6 self-start">Confirm profile and create portrait<ArrowRight size={18}/></button>}
        {(state.completed||portrait)&&<Link to="/dashboard" className="btn-primary mt-6 self-start">Go to dashboard<ArrowRight size={18}/></Link>}
      </div>
      <div className="space-y-5">
        <div className="card p-6"><h2 className="font-display text-xl font-bold">Profile in progress</h2><p className="mt-1 text-sm text-slate-500">Only details you have provided appear here.</p><dl className="mt-5 space-y-3">{Object.entries({exam:'Exam',proficiency:'Current level',target_score:'Target score',exam_date:'Exam date',weekly_hours:'Hours per week',priority_skills:'Priority skills'}).map(([key,label])=><div key={key} className="flex justify-between gap-3 border-b border-slate-100 pb-2 text-sm"><dt className="text-slate-500">{label}</dt><dd className="text-right font-semibold">{Array.isArray(state.draft[key as keyof Profile])?(state.draft.priority_skills||[]).join(', '):String(state.draft[key as keyof Profile]??'—')}</dd></div>)}</dl>{state.ready&&<p className="mt-4 flex items-center gap-2 text-sm font-semibold text-emerald-700"><CheckCircle2 size={18}/> Ready for confirmation</p>}</div>
        {portrait&&<div className="card p-6"><h2 className="font-display text-xl font-bold">Your learning portrait</h2>{portrait.state==='RELEASED'?<><p className="mt-3 text-sm text-slate-600">{portrait.payload?.summary}</p><p className="mt-3 text-sm font-semibold text-teal">Focus: {(portrait.payload?.focus_areas||[]).join(', ')}</p></>:<p className="mt-3 text-sm text-amber-700">The portrait is held for quality review. Your confirmed profile is saved.</p>}</div>}
      </div>
    </div>
  </div>
}

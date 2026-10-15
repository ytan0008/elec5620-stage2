import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, CheckCircle2, Mic, Send } from 'lucide-react'
import { Profile, Result, post, request } from './api'
import { PixelAvatar, personaName } from './pixel/Avatar'
import { moodFor, usePersona } from './persona'
import { listen, recognitionSupported, speak } from './voice'

type State = { draft: Partial<Profile>; messages: { role: string; text: string }[]; ready: boolean; completed: boolean; next_field: string | null; assistant_message: string; mode: string }
type Notify = (message: string, kind?: 'success' | 'error') => void

const choices: Record<string, string[]> = {
  exam: ['IELTS', 'TOEFL'], proficiency: ['beginner', 'intermediate', 'advanced'],
  target_score: ['6.0', '6.5', '7.0', '7.5'], weekly_hours: ['4', '6', '8', '10'],
  priority_skills: ['writing and speaking', 'reading and listening', 'all four skills'],
}

export default function OnboardingPage({ onComplete, notify }: { onComplete: () => void; notify: Notify }) {
  const { persona, aiSpeaking } = usePersona()
  const [state, setState] = useState<State | null>(null)
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false)
  const [listening, setListening] = useState(false)
  const [portrait, setPortrait] = useState<Result | null>(null)
  const bottom = useRef<HTMLDivElement | null>(null)
  useEffect(() => { request<State>('/onboarding').then(data => { setState(data); if (data.completed) onComplete() }).catch(error => notify(error.message, 'error')) }, [])
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'nearest' }) }, [state?.messages.length])
  const send = async (value: string) => {
    if (!value.trim() || busy) return
    setBusy(true)
    try { const next = await post<State>('/onboarding/message', { message: value.trim() }); setState(next); setAnswer(''); void speak(next.assistant_message, persona) }
    catch (error) { notify((error as Error).message, 'error') } finally { setBusy(false) }
  }
  const mic = () => {
    let text = ''
    setListening(true)
    const handle = listen({ onText: (f, i) => { text = `${f} ${i}`.trim(); setAnswer(text); window.setTimeout(() => handle.stop(), 2000) }, onError: m => { notify(m, 'error'); setListening(false) }, onEnd: () => { setListening(false); if (text) void send(text) } })
  }
  const confirm = async () => {
    setBusy(true)
    try { const response = await post<{ profile: Profile; portrait: Result }>('/onboarding/confirm'); setPortrait(response.portrait); onComplete(); notify('Your profile is ready') }
    catch (error) { notify((error as Error).message, 'error') } finally { setBusy(false) }
  }
  if (!state) return <div className="panel p-8 font-pixel">Summoning your coordinator…</div>
  const transcript = state.messages.length ? state.messages : [{ role: 'assistant', text: state.assistant_message }]
  return <div className="mx-auto max-w-6xl space-y-6">
    <div className="panel panel-hot flex flex-wrap items-center gap-6 p-7">
      <PixelAvatar persona={persona} mood={moodFor(aiSpeaking, listening, busy)} size={110} />
      <div className="min-w-0 flex-1"><p className="eyebrow">Learning Coordinator · {personaName(persona)}</p><h1 className="heading title-glow mt-3 text-3xl md:text-4xl">Let's build your learning profile</h1>
        <p className="mt-3 max-w-2xl font-read text-mist">Tell me about your exam goal. I'll ask one thing at a time, then prepare your starting portrait. You can type or answer with your voice.</p></div>
    </div>
    <div className="grid gap-6 lg:grid-cols-[1.25fr_.75fr]">
      <div className="panel flex min-h-[520px] flex-col p-5 md:p-7">
        <div className="flex-1 space-y-4 overflow-auto" aria-label="Profile conversation">
          {transcript.map((message, index) => <div key={index} className={`flex ${message.role === 'learner' ? 'justify-end' : 'justify-start'}`}><div className={`max-w-[85%] px-4 py-3 font-read text-[15px] leading-relaxed ${message.role === 'learner' ? 'bg-violet' : 'bg-abyss/80'}`} style={{ boxShadow: `0 0 0 2px ${message.role === 'learner' ? '#ff4fd8' : '#3ef0ff'}` }}>{message.text}</div></div>)}
          <div ref={bottom} />
        </div>
        {!state.completed && !state.ready && <div className="mt-6 border-t-4 border-plum pt-5">
          {choices[state.next_field || ''] && <div className="mb-3 flex flex-wrap gap-1">{choices[state.next_field || ''].map(choice => <button key={choice} onClick={() => send(choice)} disabled={busy} className="btn-secondary !py-1.5 text-sm">{choice}</button>)}</div>}
          <form onSubmit={event => { event.preventDefault(); send(answer) }} className="flex gap-2">
            <input aria-label="Your reply" className="input" value={answer} onChange={event => setAnswer(event.target.value)} placeholder={state.next_field === 'exam_date' ? 'YYYY-MM-DD' : 'Type your answer…'} type={state.next_field === 'exam_date' ? 'date' : 'text'} />
            {recognitionSupported() && state.next_field !== 'exam_date' && <button type="button" onClick={mic} disabled={listening} aria-label="Answer by voice" className="btn-cyan !px-3"><Mic size={17} /></button>}
            <button disabled={busy || !answer.trim()} className="btn-primary !px-3" aria-label="Send reply"><Send size={17} /></button>
          </form>
        </div>}
        {state.ready && !state.completed && !portrait && <button onClick={confirm} disabled={busy} className="btn-primary mt-6 self-start">Confirm profile and create portrait<ArrowRight size={17} /></button>}
        {(state.completed || portrait) && <Link to="/dashboard" className="btn-cyan mt-6 self-start">Go to dashboard<ArrowRight size={17} /></Link>}
      </div>
      <div className="space-y-5">
        <div className="panel panel-cyan p-6"><h2 className="section-title">Profile in progress</h2><p className="mt-1 font-read text-sm text-mist">Only details you have provided appear here.</p>
          <dl className="mt-5 space-y-3">{Object.entries({ exam: 'Exam', proficiency: 'Current level', target_score: 'Target score', exam_date: 'Exam date', weekly_hours: 'Hours per week', priority_skills: 'Priority skills' }).map(([key, label]) => <div key={key} className="flex justify-between gap-3 border-b-2 border-plum pb-2"><dt className="font-pixel text-mist">{label}</dt><dd className="text-right font-pixel text-cyan">{Array.isArray(state.draft[key as keyof Profile]) ? (state.draft.priority_skills || []).join(', ') : String(state.draft[key as keyof Profile] ?? '—')}</dd></div>)}</dl>
          {state.ready && <p className="mt-4 flex items-center gap-2 font-pixel text-lime"><CheckCircle2 size={18} /> Ready for confirmation</p>}</div>
        {portrait && <div className="panel panel-lime p-6"><h2 className="section-title">Your learning portrait</h2>{portrait.state === 'RELEASED' ? <><p className="mt-3 font-read text-sm text-mist">{portrait.payload?.summary}</p><p className="mt-3 font-pixel text-cyan">Focus: {(portrait.payload?.focus_areas || []).join(', ')}</p></> : <p className="mt-3 font-read text-sm text-sun">The portrait is held for quality review. Your confirmed profile is saved.</p>}</div>}
      </div>
    </div>
  </div>
}

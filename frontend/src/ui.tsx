import { useEffect, useState } from 'react'
import { ShieldCheck, Sparkles } from 'lucide-react'
import { Result, request } from './api'

export type Notify = (message: string, kind?: 'success' | 'error') => void
export const skills = ['listening', 'reading', 'writing', 'speaking']
export const nice = (value: string) => value.toLowerCase().replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase())
export const stamp = (value: string) => new Date(value).toLocaleString()
export const words = (text: string) => (text.trim() ? text.trim().split(/\s+/).length : 0)
export const clock = (seconds: number) => `${Math.floor(Math.max(0, seconds) / 60).toString().padStart(2, '0')}:${(Math.max(0, seconds) % 60).toString().padStart(2, '0')}`
export const SKILL_COLOR: Record<string, string> = { listening: '#3ef0ff', reading: '#b8ff5c', writing: '#ffd34d', speaking: '#ff4fd8' }

export function useLoad<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const reload = () => {
    if (!path) return
    setLoading(true)
    request<T>(path).then(value => { setData(value); setError('') }).catch(e => setError(e.message)).finally(() => setLoading(false))
  }
  useEffect(() => { reload() }, [path, ...deps])
  return { data, error, loading, reload, setData }
}

export function Spinner({ label = 'Summoning your workspace…' }: { label?: string }) {
  return <div className="flex flex-col items-center gap-4 py-14 text-mist"><div className="loader-pixel" /><span className="font-pixel">{label}</span></div>
}

export function Empty({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return <div className="panel p-10 text-center">
    <div className="mx-auto mb-4 grid h-12 w-12 place-items-center bg-plum text-sun" style={{ boxShadow: '0 0 0 3px #6b52d6' }}><Sparkles size={22} /></div>
    <h3 className="heading text-xl">{title}</h3>
    <p className="mx-auto mt-2 max-w-md font-read text-mist">{body}</p>
    {action && <div className="mt-6">{action}</div>}
  </div>
}

export function PageTitle({ eyebrow, title, subtitle, action }: { eyebrow: string; title: string; subtitle?: string; action?: React.ReactNode }) {
  return <div className="mb-8 flex flex-wrap items-end justify-between gap-4 anim-rise">
    <div className="min-w-0">
      <span className="eyebrow">{eyebrow}</span>
      <h1 className="heading title-glow mt-3 text-3xl md:text-[2.6rem] md:leading-tight">{title}</h1>
      {subtitle && <p className="mt-3 max-w-3xl font-read text-mist">{subtitle}</p>}
    </div>
    {action}
  </div>
}

export function Status({ value }: { value: string }) {
  const good = ['ACTIVE', 'RELEASED', 'RESOLVED', 'VERIFIED', 'VERIFY', 'HUMAN_APPROVED', 'CURATED', 'SUBMITTED'].includes(value)
  const wait = ['HELD', 'PENDING', 'MORE_INFO', 'HUMAN_REVIEW', 'PROPOSED', 'IN_PROGRESS', 'HOLD'].includes(value)
  return <span className={`pill ${good ? 'text-lime' : wait ? 'text-sun' : 'text-mist'}`}>{nice(value)}</span>
}

export function Metric({ label, value, icon, color = '#3ef0ff' }: { label: string; value: string; icon: React.ReactNode; color?: string }) {
  return <div className="panel panel-flat p-5">
    <div className="flex items-center justify-between font-pixel text-sm uppercase tracking-wider text-mist"><span>{label}</span><span style={{ color }}>{icon}</span></div>
    <div className="num mt-3 text-5xl" style={{ color }}>{value}</div>
  </div>
}

export function ScoreBar({ label, score, max, color = '#3ef0ff' }: { label: string; score: number; max: number; color?: string }) {
  return <div className="tile">
    <div className="flex items-baseline justify-between font-pixel"><span className="text-mist">{nice(label)}</span><span className="num text-3xl" style={{ color }}>{score}</span></div>
    <div className="bar mt-2"><span style={{ width: `${Math.min(100, score / max * 100)}%`, background: `repeating-linear-gradient(90deg, ${color} 0 6px, transparent 6px 8px)` }} /></div>
  </div>
}

export function HeldNotice({ result }: { result: Result }) {
  return <div className="panel panel-sun p-5">
    <div className="flex items-center gap-2 font-pixel text-lg text-sun"><ShieldCheck size={20} /> Quality review in progress</div>
    <p className="mt-2 font-read text-mist">{result.message || 'Your result is being double-checked by the Quality Manager and, if needed, a human instructor.'}</p>
    <div className="mt-3"><Status value={result.state} /></div>
  </div>
}

/* Feedback for writing / speaking results */
export function FeedbackPanel({ result }: { result: Result | null }) {
  if (!result) return null
  if (result.state !== 'RELEASED') return <HeldNotice result={result} />
  const p = result.payload || {}
  const max = p.score_scale?.includes('TOEFL') ? 6 : 9
  return <div className="panel panel-cyan space-y-6 p-6 anim-rise">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><span className="eyebrow">Verified feedback</span><h3 className="section-title mt-2">{result.source_mode === 'REAL' ? 'Cloud AI assessment' : 'Built-in rubric analyser'}</h3></div>
      <Status value={result.state} />
    </div>
    {p.estimated_overall !== undefined && <div className="flex items-center gap-5">
      <div className="grid h-24 w-24 place-items-center bg-abyss" style={{ boxShadow: '0 0 0 4px #ff4fd8, 6px 6px 0 4px rgba(0,0,0,.4)' }}><span className="num text-6xl text-magenta">{p.estimated_overall}</span></div>
      <div className="font-read text-sm text-mist">Estimated {p.score_scale}<br />Unofficial practice score · quality checked</div>
    </div>}
    <p className="font-read leading-7 text-moon/90">{p.summary || p.rationale}</p>
    {p.criteria && <div className="grid gap-3 sm:grid-cols-2">{Object.entries(p.criteria).map(([name, score]) => <ScoreBar key={name} label={name} score={Number(score)} max={max} />)}</div>}
    {p.analysis && Object.keys(p.analysis).length > 0 && <div className="flex flex-wrap gap-2">{Object.entries(p.analysis).filter(([, v]) => typeof v === 'number').map(([k, v]) => <span key={k} className="pill text-cyan">{nice(k)}: {String(v)}</span>)}</div>}
    {p.comments?.length > 0 && <div className="space-y-3"><h4 className="font-pixel text-lg text-sun">Examiner notes</h4>{p.comments.map((item: Record<string, string>, i: number) => <div key={i} className="tile font-read text-sm">
      <strong className="font-pixel text-base text-moon">{item.issue}</strong>
      {item.sentence && <p className="mt-1 italic text-fog">“{item.sentence}”</p>}
      <p className="mt-1 text-mist">{item.suggestion}</p>
      {item.correction && <p className="mt-1 text-lime">→ {item.correction}</p>}
    </div>)}</div>}
    {p.improved_sentences?.length > 0 && <div className="space-y-2"><h4 className="font-pixel text-lg text-lime">Level-up rewrites</h4>{p.improved_sentences.map((item: Record<string, string>, i: number) => <div key={i} className="tile font-read text-sm"><p className="text-fog line-through decoration-rose/70">{item.original}</p><p className="mt-1 text-lime">{item.improved}</p></div>)}</div>}
    {p.model_answer && <div><h4 className="font-pixel text-lg text-magenta">Higher-band model</h4><p className="tile mt-2 whitespace-pre-wrap font-read text-sm leading-6">{p.model_answer}</p></div>}
    {p.improvements?.length > 0 && <ul className="space-y-1 font-read text-sm text-mist">{p.improvements.map((item: string, i: number) => <li key={i}>▸ {item}</li>)}</ul>}
    {p.pronunciation_note && <p className="font-read text-xs text-sun">{p.pronunciation_note}</p>}
  </div>
}

export function Countdown({ seconds, running, onDone, className = '' }: { seconds: number; running: boolean; onDone?: () => void; className?: string }) {
  const [left, setLeft] = useState(seconds)
  useEffect(() => setLeft(seconds), [seconds])
  useEffect(() => {
    if (!running) return
    const id = window.setInterval(() => setLeft(value => {
      if (value <= 1) { window.clearInterval(id); onDone?.(); return 0 }
      return value - 1
    }), 1000)
    return () => window.clearInterval(id)
  }, [running])
  return <span className={`num ${left < 60 && running ? 'text-rose' : 'text-cyan'} ${className}`}>{clock(left)}</span>
}

import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Flag, X } from 'lucide-react'
import { post, request } from './api'
import { Status, stamp } from './ui'

type Report = { id: number; category: string; message: string; status: string; response: string | null; created_at: string }

/* Lets a learner flag a wrong score, a broken question or a tutor mistake for the teacher console. */
export default function ReportProblem({ category, context = {}, label = 'Report a problem' }: { category: 'result' | 'question' | 'tutor' | 'audio' | 'other'; context?: Record<string, string | number>; label?: string }) {
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | string>('idle')
  const send = async () => {
    setState('sending')
    try { await post('/feedback', { category, message, context: { ...context, page: window.location.pathname } }); setState('sent'); setMessage('') } catch (e) { setState((e as Error).message) }
  }
  return <>
    <button type="button" onClick={() => { setOpen(true); setState('idle') }} className="btn-ghost !px-0 text-xs text-fog hover:text-sun"><Flag size={13} /> {label}</button>
    {open && createPortal(<div className="anim-fade fixed inset-0 z-[95] flex items-center justify-center bg-black/70 p-5" onClick={() => setOpen(false)}>
      <form className="anim-pop panel panel-sun w-full max-w-md space-y-3 p-6" role="dialog" aria-label="Report a problem" onClick={e => e.stopPropagation()} onSubmit={e => { e.preventDefault(); void send() }}>
        <div className="flex items-center justify-between"><h2 className="section-title flex items-center gap-2"><Flag size={18} className="text-sun" /> Report a problem</h2><button type="button" aria-label="Close" onClick={() => setOpen(false)}><X /></button></div>
        {state === 'sent' ? <p className="tile font-read text-lime">Thanks! Your teacher will review it. Replies appear in Settings → My reports.</p> : <>
          <p className="font-read text-sm text-mist">Tell the teacher what looks wrong (e.g. a score that seems unfair, an answer key mistake, or an incorrect tutor explanation).</p>
          <textarea aria-label="Describe the problem" className="input min-h-28" value={message} onChange={e => setMessage(e.target.value)} placeholder="What happened?" />
          {state !== 'idle' && state !== 'sending' && <p className="font-read text-xs text-rose">{state}</p>}
          <button className="btn-sun w-full" disabled={message.trim().length < 5 || state === 'sending'}>{state === 'sending' ? 'Sending…' : 'Send report'}</button>
        </>}
      </form>
    </div>, document.body)}
  </>
}

export function MyReports() {
  const [reports, setReports] = useState<Report[] | null>(null)
  useEffect(() => { request<Report[]>('/feedback').then(setReports).catch(() => setReports([])) }, [])
  return <div className="panel p-6">
    <div className="flex items-center justify-between gap-3"><h2 className="section-title">My reports</h2><ReportProblem category="other" label="New report" /></div>
    <div className="mt-3 space-y-2">{!reports ? <div className="skeleton h-10" /> : !reports.length ? <p className="font-read text-sm text-mist">You haven't reported any problems.</p>
      : reports.map(r => <div key={r.id} className="tile font-read text-sm"><div className="flex items-center justify-between gap-2"><span className="font-pixel text-xs uppercase text-cyan">{r.category} · {stamp(r.created_at)}</span><Status value={r.status} /></div>
        <p className="mt-1">{r.message}</p>{r.response && <p className="mt-1 text-lime">Teacher: {r.response}</p>}</div>)}</div>
  </div>
}

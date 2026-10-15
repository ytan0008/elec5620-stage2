import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Clock3, RotateCcw, Send } from 'lucide-react'
import { Practice, Result, post, request } from '../api'
import { Countdown, Empty, FeedbackPanel, Notify, PageTitle, Spinner, Status, words } from '../ui'
import ChartView from './ChartView'
import { useExamLock } from '../examLock'

type Attempt = { id: number; attempt: number; text: string; result: Result; created_at: string }

export default function WritingPractice({ notify }: { notify: Notify }) {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [practice, setPractice] = useState<Practice | null>(null)
  const [text, setText] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const [attempts, setAttempts] = useState<Attempt[]>([])
  const [busy, setBusy] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  useExamLock('writing', running && !result)

  const load = async (fresh = false) => {
    setBusy(true); setError(''); setResult(null); setRunning(false)
    try {
      const stored = !params.get('question') ? localStorage.getItem('last-writing') : null
      const sessionId = !fresh && (params.get('session') || stored)
      const question = !fresh && params.get('question')
      const item = sessionId ? await request<Practice>(`/practice/${sessionId}`) : await post<Practice>(`/practice/writing${question ? `?question_id=${question}` : ''}`)
      setPractice(item)
      localStorage.setItem('last-writing', String(item.id))
      if (String(item.id) !== params.get('session')) navigate(`/practice/writing?session=${item.id}`, { replace: true })
      setText(localStorage.getItem(`draft-${item.id}`) || '')
      const history = await request<Attempt[]>(`/practice/${item.id}/attempts`)
      setAttempts(history)
      if (history.length) setResult(history[history.length - 1].result)
    } catch (e) {
      if (!fresh && !params.get('session') && localStorage.getItem('last-writing')) { localStorage.removeItem('last-writing'); return load(true) }
      setError((e as Error).message)
    } finally { setBusy(false) }
  }
  useEffect(() => { void load() }, [])

  const update = (value: string) => { setText(value); if (practice) localStorage.setItem(`draft-${practice.id}`, value) }
  const submit = async () => {
    if (!practice) return
    setBusy(true); setRunning(false)
    try {
      const response = await post<{ result: Result }>(`/practice/${practice.id}/submit`, { text, task: practice.prompt.task })
      setResult(response.result)
      setAttempts(await request<Attempt[]>(`/practice/${practice.id}/attempts`))
      notify(response.result.state === 'RELEASED' ? 'Feedback released' : 'Held for quality review')
    } catch (e) { notify((e as Error).message, 'error') } finally { setBusy(false) }
  }

  if (error) return <Empty title="Could not load the task" body={error} action={<button className="btn-primary" onClick={() => load(true)}>Try another task</button>} />
  if (!practice) return <Spinner label="Opening your writing desk…" />
  const prompt = practice.prompt
  const minimum = prompt.min_words || 250
  const count = words(text)
  const verified = attempts.filter(a => a.result.state === 'RELEASED' && a.result.payload?.estimated_overall !== undefined)
  const delta = verified.length >= 2 ? Number(verified[verified.length - 1].result.payload!.estimated_overall) - Number(verified[verified.length - 2].result.payload!.estimated_overall) : null
  return <>
    <PageTitle eyebrow={`Writing · ${prompt.task_type || ''}`} title={prompt.title} subtitle={`Write at least ${minimum} words. Suggested time: ${Math.round(prompt.duration_seconds / 60)} minutes.`}
      action={<div className="flex flex-wrap gap-2"><Link to="/questions" className="btn-secondary">Question bank</Link><button className="btn-sun" onClick={() => load(true)} disabled={busy}><RotateCcw size={16} /> New task</button></div>} />
    <div className="grid gap-6 xl:grid-cols-[1.1fr_.9fr]">
      <div className="space-y-5">
        <div className="panel panel-sun space-y-4 p-6">
          <div className="flex items-center justify-between gap-3"><span className="eyebrow">Task</span>
            <span className="flex items-center gap-2"><Clock3 size={16} className="text-cyan" /><Countdown seconds={prompt.duration_seconds} running={running} className="text-3xl" onDone={() => notify('Time is up — finish your last sentence and submit.', 'error')} />
              <button className="btn-secondary !py-1 text-xs" onClick={() => setRunning(v => !v)}>{running ? 'Pause' : 'Start timer'}</button></span>
          </div>
          <p className="reading whitespace-pre-line">{prompt.text}</p>
          {prompt.chart && <ChartView chart={prompt.chart} />}
        </div>
        <div className="panel p-6">
          <label className="label" htmlFor="essay">Essay editor</label>
          <textarea id="essay" className="input min-h-[22rem] resize-y leading-7" value={text} onChange={e => { update(e.target.value); if (!running && !result) setRunning(true) }} placeholder="Start writing here… paragraphs separated by a blank line." spellCheck={false} />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <span className={`font-pixel ${count >= minimum ? 'text-lime' : 'text-sun'}`}>{count} / {minimum} words · draft autosaved</span>
            <button className="btn-primary" disabled={busy || text.trim().length < 8} onClick={submit}><Send size={16} /> {busy ? 'Assessing…' : 'Submit for feedback'}</button>
          </div>
        </div>
      </div>
      <div className="space-y-5">
        <FeedbackPanel result={result} />
        {attempts.length > 0 && <div className="panel p-6">
          <h3 className="section-title">Revision history</h3>
          {delta !== null && <p className={`mt-3 font-pixel ${delta >= 0 ? 'text-lime' : 'text-rose'}`}>Change since previous verified attempt: {delta > 0 ? '+' : ''}{delta.toFixed(1)}</p>}
          <div className="mt-4 space-y-3">{attempts.map(a => <button key={a.id} className="tile w-full text-left" onClick={() => { setResult(a.result); update(a.text) }}>
            <div className="flex justify-between font-pixel"><span>Attempt {a.attempt}</span><Status value={a.result.state} /></div>
            <p className="mt-1 line-clamp-2 font-read text-sm text-mist">{a.text}</p>
            {a.result.payload?.estimated_overall !== undefined && <p className="mt-1 font-pixel text-cyan">Estimate {a.result.payload.estimated_overall}</p>}
          </button>)}</div>
        </div>}
        {!result && <div className="panel panel-flat p-6 font-read text-sm text-mist">
          <h3 className="font-pixel text-lg text-sun">Checklist</h3>
          <ul className="mt-2 space-y-1">{prompt.task === 'task1'
            ? ['Paraphrase the chart in your first sentence', 'Write an overview of the main trends', 'Compare figures — no opinions'].map(t => <li key={t}>▸ {t}</li>)
            : ['Answer every part of the question', 'State a clear position', 'One main idea per paragraph, with an example', 'Conclude without new ideas'].map(t => <li key={t}>▸ {t}</li>)}</ul>
        </div>}
      </div>
    </div>
  </>
}

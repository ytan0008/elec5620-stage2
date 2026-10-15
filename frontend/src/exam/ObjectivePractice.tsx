import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowRight, BookOpen, Clock3, Eye, Headphones, RotateCcw, Send } from 'lucide-react'
import { ObjectiveTest, Practice, Result, Section, post, request } from '../api'
import { Countdown, Empty, HeldNotice, Notify, PageTitle, Spinner, Status } from '../ui'
import ListeningPlayer, { useClipPlayer } from './ListeningPlayer'
import { useExamLock } from '../examLock'
import ReportProblem from '../ReportProblem'
import { Answers, ReviewItem, SectionQuestions, answeredCount, questionCount } from './Questions'

export function Transcript({ sections, evidence }: { sections: { title: string; script: { speaker: string; text: string }[]; clips?: { speaker: string; text: string }[][] }[]; evidence: string[] }) {
  const mark = (text: string) => {
    const hit = evidence.find(item => item && item.length > 8 && text.includes(item))
    if (!hit) return text
    const [before, after] = text.split(hit)
    return <>{before}<mark className="bg-sun/90 px-0.5 text-night">{hit}</mark>{after}</>
  }
  return <div className="space-y-5">{sections.map(section => <div key={section.title}>
    <h4 className="font-pixel text-lg text-cyan">{section.title}</h4>
    <div className="mt-2 space-y-2 font-read text-sm leading-6">
      {section.script.map((line, i) => <p key={i}><b className={`font-pixel ${line.speaker === 'Narrator' ? 'text-fog' : 'text-magenta'}`}>{line.speaker}:</b> {mark(line.text)}</p>)}
      {section.clips?.map((clip, i) => <p key={`c${i}`}><b className="font-pixel text-magenta">Recording {i + 1}:</b> {clip.map(line => line.text).join(' ')}</p>)}
    </div>
  </div>)}</div>
}

export function Passage({ section, evidence = [] }: { section: Section; evidence?: string[] }) {
  return <article className="space-y-4">
    <h2 className="heading text-2xl text-sun">{section.title}</h2>
    {section.passage?.map((paragraph, i) => {
      const hit = evidence.find(item => item && item.length > 8 && paragraph.text.includes(item))
      const parts = hit ? paragraph.text.split(hit) : [paragraph.text]
      return <p key={i} className="reading whitespace-pre-line">{paragraph.label && <b className="mr-2 font-arcade text-xs text-cyan">{paragraph.label}</b>}{parts[0]}{hit && <mark className="bg-sun/90 px-0.5 text-night">{hit}</mark>}{parts[1]}</p>
    })}
  </article>
}

export default function ObjectivePractice({ skill, notify }: { skill: 'listening' | 'reading'; notify: Notify }) {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [practice, setPractice] = useState<Practice | null>(null)
  const [answers, setAnswersState] = useState<Answers>({})
  const [result, setResult] = useState<Result | null>(null)
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState<'exam' | 'practice'>('practice')
  const [started, setStarted] = useState(false)
  const [showScript, setShowScript] = useState(false)
  const [error, setError] = useState('')
  const clips = useClipPlayer(mode)
  useExamLock(`objective-${skill}`, started && !result)
  const isListening = skill === 'listening'

  const load = async (fresh = false) => {
    setBusy(true); setError(''); setResult(null); setStarted(false); setShowScript(false)
    try {
      const sessionId = !fresh && (params.get('session') || (!params.get('question') && localStorage.getItem(`last-${skill}`)))
      const question = !fresh && params.get('question')
      const item = sessionId ? await request<Practice>(`/practice/${sessionId}`) : await post<Practice>(`/practice/${skill}${question ? `?question_id=${question}` : ''}`)
      setPractice(item)
      localStorage.setItem(`last-${skill}`, String(item.id))
      if (String(item.id) !== params.get('session')) navigate(`/practice/${skill}?session=${item.id}`, { replace: true })
      try { setAnswersState(JSON.parse(localStorage.getItem(`answers-${item.id}`) || '{}')) } catch { setAnswersState({}) }
      const attempts = await request<{ result: Result }[]>(`/practice/${item.id}/attempts`)
      if (attempts.length) { setResult(attempts[attempts.length - 1].result); setStarted(true) }
    } catch (e) {
      if (!fresh && !params.get('session') && localStorage.getItem(`last-${skill}`)) { localStorage.removeItem(`last-${skill}`); return load(true) }
      setError((e as Error).message)
    } finally { setBusy(false) }
  }
  useEffect(() => { void load() }, [skill])

  const test: ObjectiveTest | undefined = practice?.prompt.test
  const setAnswer = (n: number, value: string) => {
    if (!practice) return
    setAnswersState(previous => { const next = { ...previous, [String(n)]: value }; localStorage.setItem(`answers-${practice.id}`, JSON.stringify(next)); return next })
  }
  const review = useMemo(() => Object.fromEntries(((result?.payload?.review || []) as ReviewItem[]).map(item => [item.n, item])), [result])
  const evidence = ((result?.payload?.review || []) as ReviewItem[]).map(item => item.evidence)
  const submit = async () => {
    if (!practice) return
    setBusy(true)
    try {
      const response = await post<{ result: Result }>(`/practice/${practice.id}/submit`, { answers })
      setResult(response.result)
      notify(response.result.state === 'RELEASED' ? 'Marked! Review each answer below.' : 'Submitted for quality review')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) { notify((e as Error).message, 'error') } finally { setBusy(false) }
  }

  const Icon = isListening ? Headphones : BookOpen
  if (error) return <Empty title="Could not load the test" body={error} action={<button className="btn-primary" onClick={() => load(true)}>Try another test</button>} />
  if (!practice || !test) return busy ? <Spinner label="Opening the test…" /> : <Empty title={`Ready for ${skill}?`} body="Pick a test from the bank or start a fresh one." action={<button className="btn-primary" onClick={() => load(true)}>Start</button>} />
  const total = questionCount(test.sections)
  const done = result?.state === 'RELEASED'
  const p = result?.payload || {}
  return <>
    <PageTitle eyebrow={`${test.exam} ${skill} · ${practice.prompt.task_type || ''}`} title={practice.prompt.title}
      subtitle={isListening ? 'Recorded with distinct speakers. Choose exam mode to hear it once, exactly like the test, or practice mode to pause, replay and slow down.' : 'Read the passage and answer every question. Answers must come from the passage, not general knowledge.'}
      action={<div className="flex flex-wrap gap-2"><Link to="/questions" className="btn-secondary">Question bank</Link><button className="btn-sun" onClick={() => load(true)} disabled={busy}><RotateCcw size={16} /> New test</button></div>} />

    {result && !done && <div className="mb-6"><HeldNotice result={result} /></div>}
    {done && <div className="panel panel-hot mb-6 flex flex-wrap items-center gap-6 p-6 anim-rise">
      <div className="grid h-28 w-28 place-items-center bg-abyss" style={{ boxShadow: '0 0 0 4px #ff4fd8' }}><span className="num text-7xl text-magenta">{p.estimated_overall}</span></div>
      <div className="min-w-0 flex-1 space-y-2">
        <p className="font-pixel text-2xl">{p.raw_score} / {p.total} correct</p>
        <p className="font-read text-mist">{p.summary}</p>
        <div className="flex flex-wrap gap-2">{Object.entries(p.question_types || {}).map(([k, v]) => <span key={k} className="pill text-cyan">{k}: {String(v)}</span>)}<Status value={result!.state} /></div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          {p.raw_score < p.total && <Link to="/notebook?tab=mistake" className="btn-ghost !px-0">{p.total - p.raw_score} wrong answer(s) saved to your Mistake book →</Link>}
          <ReportProblem category="question" context={{ package_id: result!.id, test: practice.prompt.title }} label="Answer key looks wrong?" />
        </div>
      </div>
      <button className="btn-primary" onClick={() => load(true)}>Next test <ArrowRight size={16} /></button>
    </div>}

    {!started && !result ? <div className="panel mx-auto max-w-2xl space-y-5 p-8 text-center">
      <Icon size={40} className="mx-auto text-cyan" />
      <h2 className="heading text-2xl">{total} questions{test.minutes ? ` · ${test.minutes} minutes` : ''}</h2>
      <p className="font-read text-mist">{practice.prompt.text}</p>
      {isListening && <div className="flex flex-wrap justify-center gap-2">
        {(['exam', 'practice'] as const).map(value => <button key={value} onClick={() => setMode(value)} className={value === mode ? 'btn-primary' : 'btn-secondary'}>{value === 'exam' ? 'Exam mode · play once' : 'Practice mode · replay'}</button>)}
      </div>}
      <button className="btn-cyan" onClick={() => setStarted(true)}>Begin <ArrowRight size={16} /></button>
    </div> : <div className={`grid gap-6 ${isListening ? 'lg:grid-cols-[1fr]' : 'lg:grid-cols-2'}`}>
      {isListening ? <div className="space-y-4">
        {!done && <ListeningPlayer sections={test.sections} mode={mode} />}
        {done && <div className="panel p-5">
          <button className="btn-ghost" onClick={() => setShowScript(value => !value)}><Eye size={16} /> {showScript ? 'Hide' : 'Show'} transcript with answer evidence</button>
          {showScript && <div className="mt-4"><Transcript sections={p.transcript || []} evidence={evidence} /></div>}
          {done && <div className="mt-4"><ListeningPlayer sections={test.sections} mode="practice" /></div>}
        </div>}
      </div> : <div className="panel max-h-[75vh] overflow-y-auto p-6">{test.sections.map(section => <Passage key={section.id} section={section} evidence={done ? evidence : []} />)}</div>}

      <div className={`panel p-6 ${isListening ? '' : 'max-h-[75vh] overflow-y-auto'}`}>
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <span className="font-pixel text-mist">{answeredCount(test.sections, answers)} / {total} answered</span>
          {!result && test.minutes && <span className="flex items-center gap-2 font-pixel"><Clock3 size={16} className="text-cyan" /><Countdown seconds={test.minutes * 60} running={started && !result} className="text-3xl" onDone={() => notify('Time is up! Submit your answers.', 'error')} /></span>}
        </div>
        {test.sections.map(section => <div key={section.id} className="mb-8">
          {test.sections.length > 1 && <h3 className="mb-3 font-arcade text-xs text-magenta">{section.title}</h3>}
          <SectionQuestions section={section} answers={answers} setAnswer={setAnswer} disabled={!!result} review={done ? review : undefined} onPlayClip={q => clips.play(q)} />
        </div>)}
        {!result && <button className="btn-primary w-full" disabled={busy} onClick={submit}><Send size={17} /> {busy ? 'Marking…' : 'Submit answers'}</button>}
      </div>
    </div>}
  </>
}

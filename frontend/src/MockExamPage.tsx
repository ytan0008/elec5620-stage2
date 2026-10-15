import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, ChevronRight, Clock3, FileText, Send } from 'lucide-react'
import { Mock, ObjectiveTest, WritingTask, post, put, request } from './api'
import { HeldNotice, Notify, PageTitle, ScoreBar, Spinner, Status, clock, nice, words } from './ui'
import ListeningPlayer, { useClipPlayer } from './exam/ListeningPlayer'
import { Answers, ReviewItem, SectionQuestions, answeredCount, questionCount } from './exam/Questions'
import { Passage, Transcript } from './exam/ObjectivePractice'
import ChartView from './exam/ChartView'
import SpeakingStudio from './exam/SpeakingStudio'
import { useExamLock } from './examLock'

const SECTIONS = ['listening', 'reading', 'writing', 'speaking'] as const
const parse = (value?: string) => { try { return JSON.parse(value || '{}') } catch { return {} } }

function Results({ exam }: { exam: Mock }) {
  const result = exam.result!
  const [open, setOpen] = useState<string>('listening')
  if (result.state !== 'RELEASED') return <HeldNotice result={result} />
  const p = result.payload || {}
  const max = exam.exam === 'IELTS' ? 9 : 6
  const details = p.details || {}
  return <div className="space-y-6">
    <div className="panel panel-hot flex flex-wrap items-center gap-6 p-6">
      <div className="grid h-32 w-32 place-items-center bg-abyss" style={{ boxShadow: '0 0 0 4px #ff4fd8' }}><span className="num text-8xl text-magenta">{p.estimated_overall}</span></div>
      <div className="min-w-0 flex-1"><span className="eyebrow">Overall estimate · {p.score_scale}</span><p className="mt-3 font-pixel text-2xl">{p.readiness}</p><p className="mt-2 font-read text-sm text-mist">{p.summary}</p></div>
    </div>
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{Object.entries(p.section_scores || {}).map(([skill, score]) => <ScoreBar key={skill} label={skill} score={Number(score)} max={max} />)}</div>
    {details.listening && <div className="panel p-6">
      <div className="flex flex-wrap gap-2">{SECTIONS.map(s => <button key={s} className={open === s ? 'btn-primary' : 'btn-secondary'} onClick={() => setOpen(s)}>{nice(s)}</button>)}</div>
      <div className="mt-5 space-y-4 font-read">
        {(open === 'listening' || open === 'reading') && <>
          <p>{details[open].summary}</p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{(details[open].review as ReviewItem[]).map(item => <div key={item.n} className={`tile text-sm ${item.correct ? '' : 'tile-hot'}`}><b className="font-pixel">{item.n}.</b> {item.correct ? <span className="text-lime">✓ {item.given}</span> : <><span className="text-rose line-through">{item.given || '—'}</span> → <span className="text-lime">{item.answer}</span></>}</div>)}</div>
          {open === 'listening' && details.listening.transcript && <details className="tile"><summary className="cursor-pointer font-pixel text-cyan">Transcript</summary><div className="mt-3"><Transcript sections={details.listening.transcript} evidence={(details.listening.review as ReviewItem[]).map(r => r.evidence)} /></div></details>}
        </>}
        {open === 'writing' && Object.entries(details.writing || {}).map(([task, fb]: [string, any]) => <div key={task} className="tile space-y-2"><p className="font-pixel text-lg text-sun">{task === 'task1' ? 'Task 1' : task === 'task2' ? 'Task 2' : nice(task)} · band {fb.band}</p><p>{fb.summary}</p>{fb.comments?.map((c: any, i: number) => <p key={i} className="text-sm text-mist">▸ <b>{c.issue}</b>: {c.suggestion}</p>)}</div>)}
        {open === 'speaking' && details.speaking && <div className="tile space-y-2"><p>{details.speaking.summary}</p><div className="flex flex-wrap gap-2">{Object.entries(details.speaking.criteria || {}).map(([k, v]) => <span key={k} className="pill text-cyan">{nice(k)} {String(v)}</span>)}</div>{details.speaking.comments?.map((c: any, i: number) => <p key={i} className="text-sm text-mist">▸ <b>{c.issue}</b>: {c.suggestion}</p>)}<p className="text-xs text-sun">{details.speaking.pronunciation_note}</p></div>}
      </div>
    </div>}
  </div>
}

export default function MockExamPage({ notify }: { notify: Notify }) {
  const [exams, setExams] = useState<Mock[] | null>(null)
  const [exam, setExam] = useState<Mock | null>(null)
  const [section, setSection] = useState<typeof SECTIONS[number]>('listening')
  const [answers, setAnswers] = useState<Record<string, Answers>>({})
  const [task, setTask] = useState(0)
  const [part, setPart] = useState(0)
  const [busy, setBusy] = useState(false)
  const [now, setNow] = useState(Date.now())
  const saveTimer = useRef(0)
  const clips = useClipPlayer('exam')
  useExamLock('mock', Boolean(exam && !exam.legacy && exam.status === 'IN_PROGRESS'))

  const open = (item: Mock) => {
    setExam(item)
    setAnswers(Object.fromEntries(SECTIONS.filter(s => s !== 'speaking').map(s => [s, parse(item.answers[s])])))
  }
  useEffect(() => {
    request<Mock[]>('/mock-exams').then(list => { setExams(list); const active = list.find(m => m.status === 'IN_PROGRESS' && !m.legacy); if (active) open(active) }).catch(e => notify(e.message, 'error'))
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [])

  const create = async (length: 'short' | 'full') => {
    setBusy(true)
    try { const created = await post<Mock>('/mock-exams', { length }); open(created); setSection('listening'); setExams(prev => [created, ...(prev || [])]); notify(`${length === 'full' ? 'Full-length' : 'Short'} mock started — good luck!`) }
    catch (e) { notify((e as Error).message, 'error') } finally { setBusy(false) }
  }
  const save = (skill: string, value: Answers) => {
    if (!exam) return
    window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(() => { put(`/mock-exams/${exam.id}/${skill}`, { answer: JSON.stringify(value) }).catch(e => notify(e.message, 'error')) }, 900)
  }
  const setAnswer = (skill: string, key: string, value: string) => setAnswers(prev => { const next = { ...prev, [skill]: { ...(prev[skill] || {}), [key]: value } }; save(skill, next[skill]); return next })
  const reload = async () => { if (exam) open(await request<Mock>(`/mock-exams/${exam.id}`)) }
  const submit = async () => {
    if (!exam) return
    setBusy(true)
    try {
      window.clearTimeout(saveTimer.current)
      for (const skill of ['listening', 'reading', 'writing']) await put(`/mock-exams/${exam.id}/${skill}`, { answer: JSON.stringify(answers[skill] || {}) })
      const done = await post<Mock>(`/mock-exams/${exam.id}/submit`)
      open(done); notify('Mock exam marked')
    } catch (e) { notify((e as Error).message, 'error') } finally { setBusy(false) }
  }

  const listening: ObjectiveTest | undefined = exam?.sections.listening
  const reading: ObjectiveTest | undefined = exam?.sections.reading
  const tasks: WritingTask[] = exam?.sections.writing?.tasks || []
  const remaining = exam ? Math.max(0, Math.round((new Date(exam.created_at).getTime() + exam.duration_seconds * 1000 - now) / 1000)) : 0
  const progress = useMemo(() => exam ? {
    listening: listening ? `${answeredCount(listening.sections, answers.listening || {})}/${questionCount(listening.sections)}` : '',
    reading: reading ? `${answeredCount(reading.sections, answers.reading || {})}/${questionCount(reading.sections)}` : '',
    writing: tasks.map(t => words(answers.writing?.[t.task] || '')).join(' + ') + ' words',
    speaking: exam.answers.speaking ? 'saved' : 'not started',
  } : {}, [exam, answers]) as Record<string, string>

  if (!exams) return <Spinner label="Loading the exam hall…" />
  if (!exam || exam.legacy) return <>
    <PageTitle eyebrow="Assessment rehearsal" title="Mock examination" subtitle="A computer-delivered exam in the real format: recorded listening with multiple speakers, authentic reading question types, both writing tasks and a live spoken interview with your pixel examiner." />
    <div className="grid gap-6 md:grid-cols-2">
      <div className="panel panel-cyan space-y-4 p-7"><h2 className="heading text-2xl">Short mock · ~90 min</h2><p className="font-read text-mist">2 listening parts (20 questions), 1 reading passage, Writing Task 2, full speaking test. Ideal weekly check-in.</p><button className="btn-cyan" disabled={busy} onClick={() => create('short')}>Start short mock <ChevronRight size={17} /></button></div>
      <div className="panel panel-hot space-y-4 p-7"><h2 className="heading text-2xl">Full mock · ~2 h 45 min</h2><p className="font-read text-mist">All 4 listening parts (40 questions), 3 reading passages (40 questions), Writing Task 1 + Task 2 and the full speaking test — like test day.</p><button className="btn-primary" disabled={busy} onClick={() => create('full')}>Start full mock <ChevronRight size={17} /></button></div>
    </div>
    <p className="mt-4 font-read text-sm text-fog">You need an active learning plan first. <Link to="/plans" className="text-cyan underline">Open learning plan</Link>. Results are unofficial estimates.</p>
    {exams.filter(m => m.result).length > 0 && <div className="panel mt-8 p-6"><h2 className="section-title">Past mocks</h2><div className="mt-4 space-y-2">{exams.filter(m => m.result).map(m => <button key={m.id} className="tile flex w-full items-center justify-between text-left" onClick={() => open(m)}><span className="font-pixel">#{m.id} · {m.exam} {m.length} · {new Date(m.created_at).toLocaleDateString()}</span><span className="flex items-center gap-3">{m.result?.payload?.estimated_overall !== undefined && <b className="num text-3xl text-magenta">{m.result.payload.estimated_overall}</b>}<Status value={m.result!.state} /></span></button>)}</div></div>}
  </>

  const submitted = exam.status !== 'IN_PROGRESS'
  return <div className="space-y-5">
    <div className="panel panel-hot sticky top-2 z-20 flex flex-wrap items-center justify-between gap-4 p-4">
      <div><p className="eyebrow">Unofficial computer-delivered practice</p><h1 className="mt-2 font-pixel text-xl">{exam.exam} {exam.length === 'full' ? 'full-length' : 'short'} mock #{exam.id}</h1></div>
      <div className="flex flex-wrap items-center gap-3">
        {!submitted && <span className={`flex items-center gap-2 px-3 py-1 ${remaining < 600 ? 'bg-rose text-night' : 'bg-abyss'}`} style={{ boxShadow: '0 0 0 3px #3ef0ff' }}><Clock3 size={18} /><span className="num text-4xl">{clock(remaining)}</span></span>}
        {!submitted ? <button className="btn-primary" disabled={busy} onClick={submit}><Send size={16} /> {busy ? 'Marking…' : 'Submit all sections'}</button> : <button className="btn-secondary" onClick={() => setExam(null)}>Back to exam hall</button>}
      </div>
    </div>
    {submitted ? (exam.result ? <Results exam={exam} /> : <Spinner />) : <>
      <nav className="flex flex-wrap gap-1" aria-label="Exam sections">{SECTIONS.map((s, i) => <button key={s} onClick={() => setSection(s)} className={section === s ? 'btn-primary' : 'btn-secondary'}>
        <span className="font-arcade text-[10px]">{i + 1}</span> {nice(s)} <span className="font-read text-xs normal-case opacity-80">{progress[s]}</span>{s === 'speaking' && exam.answers.speaking && <Check size={15} />}
      </button>)}</nav>

      <div style={{ display: section === 'listening' ? undefined : 'none' }}>{listening && <div className="space-y-5">
        <ListeningPlayer sections={listening.sections} mode="exam" />
        <div className="panel p-6">{listening.sections.map(s => <div key={s.id} className="mb-8"><h3 className="mb-3 font-arcade text-xs text-magenta">{s.title}</h3>
          <SectionQuestions section={s} answers={answers.listening || {}} setAnswer={(n, v) => setAnswer('listening', String(n), v)} onPlayClip={q => clips.play(q)} /></div>)}</div>
      </div>}</div>

      {section === 'reading' && reading && <div className="space-y-3">
        {reading.sections.length > 1 && <div className="flex gap-1">{reading.sections.map((s, i) => <button key={s.id} className={part === i ? 'btn-cyan' : 'btn-secondary'} onClick={() => setPart(i)}>Passage {i + 1}</button>)}</div>}
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="panel max-h-[72vh] overflow-y-auto p-6"><Passage section={reading.sections[Math.min(part, reading.sections.length - 1)]} /></div>
          <div className="panel max-h-[72vh] overflow-y-auto p-6"><SectionQuestions section={reading.sections[Math.min(part, reading.sections.length - 1)]} answers={answers.reading || {}} setAnswer={(n, v) => setAnswer('reading', String(n), v)} /></div>
        </div>
      </div>}

      {section === 'writing' && <div className="space-y-3">
        {tasks.length > 1 && <div className="flex gap-1">{tasks.map((t, i) => <button key={t.id} className={task === i ? 'btn-cyan' : 'btn-secondary'} onClick={() => setTask(i)}>{t.task === 'task1' ? 'Task 1' : t.task === 'task2' ? 'Task 2' : nice(t.task)}</button>)}</div>}
        {tasks[task] && <div className="grid gap-5 xl:grid-cols-2">
          <div className="panel panel-sun space-y-4 p-6"><span className="eyebrow">{tasks[task].title} · {tasks[task].minutes} min suggested</span><p className="reading whitespace-pre-line">{tasks[task].prompt}</p>{tasks[task].chart && <ChartView chart={tasks[task].chart!} />}</div>
          <div className="panel p-6"><label className="label" htmlFor="mock-writing"><FileText size={14} className="mr-1 inline" />Your response</label>
            <textarea id="mock-writing" className="input min-h-[24rem] leading-7" value={answers.writing?.[tasks[task].task] || ''} onChange={e => setAnswer('writing', tasks[task].task, e.target.value)} spellCheck={false} />
            <p className={`mt-2 font-pixel ${words(answers.writing?.[tasks[task].task] || '') >= tasks[task].min_words ? 'text-lime' : 'text-sun'}`}>{words(answers.writing?.[tasks[task].task] || '')} / {tasks[task].min_words} words · autosaved</p></div>
        </div>}
      </div>}

      {section === 'speaking' && (exam.answers.speaking
        ? <div className="panel panel-lime p-6 font-pixel text-lime">Speaking section complete and saved. <span className="font-read text-mist">Submit the exam when the other sections are done.</span></div>
        : <SpeakingStudio notify={notify} mockId={exam.id} onSaved={reload} />)}
    </>}
  </div>
}

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, BookOpen, ExternalLink, FileText, Headphones, Mic, Sparkles } from 'lucide-react'
import { Health, Profile, health, post, request } from './api'
import { Notify, PageTitle, SKILL_COLOR, Spinner, nice } from './ui'

type Item = { id: number; exam: string; skill: string; task_type: string; title: string; prompt: string | null; topic: string; source_kind: string; source_url: string | null; available: boolean; verification_state: string; structured: boolean }
const ICONS: Record<string, typeof Mic> = { listening: Headphones, reading: BookOpen, writing: FileText, speaking: Mic }
const SOURCE: Record<string, [string, string]> = { OFFICIAL_LINK: ['Official sample', 'text-cyan'], ORIGINAL: ['Exam-format original', 'text-lime'], AI_GENERATED: ['AI generated', 'text-magenta'], LOCAL_GENERATED: ['Generated', 'text-sun'] }

export default function QuestionBankPage({ notify }: { notify: Notify }) {
  const navigate = useNavigate()
  const [items, setItems] = useState<Item[] | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [info, setInfo] = useState<Health | null>(null)
  const [skill, setSkill] = useState('all')
  const [topic, setTopic] = useState('urban wildlife')
  const [genSkill, setGenSkill] = useState('writing')
  const [task, setTask] = useState('auto')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    request<Item[]>('/questions').then(setItems).catch(e => notify(e.message, 'error'))
    request<Profile>('/profile').then(setProfile).catch(() => {})
    health().then(setInfo).catch(() => {})
  }, [])
  const cloud = info?.mode === 'REAL'
  const needsCloud = (genSkill === 'listening' || genSkill === 'reading') && !cloud
  const generate = async () => {
    setBusy(true)
    try {
      const item = await post<Item>('/questions/generate', { skill: genSkill, topic, task })
      setItems(prev => [item, ...(prev || [])])
      notify(item.available ? 'New task created and quality-checked' : 'Generated task is held for quality review')
    } catch (e) { notify((e as Error).message, 'error') } finally { setBusy(false) }
  }
  const start = (item: Item) => navigate(`/practice/${item.skill}?question=${item.id}`)
  const tasks: Record<string, [string, string][]> = {
    writing: profile?.exam === 'TOEFL' ? [['auto', 'Any'], ['email', 'Write an Email'], ['discussion', 'Academic Discussion']] : [['auto', 'Task 2'], ['task1', 'Task 1 (chart)'], ['task2', 'Task 2']],
    listening: profile?.exam === 'TOEFL' ? [['auto', 'Any']] : [['auto', 'Any part'], ['part1', 'Part 1'], ['part2', 'Part 2'], ['part3', 'Part 3'], ['part4', 'Part 4']],
    reading: [['auto', 'Passage']], speaking: [['auto', 'Full test']],
  }
  return <>
    <PageTitle eyebrow={`${profile?.exam || ''} question bank`} title="Question bank" subtitle="Complete exam-format tasks: multi-speaker listening parts, academic passages with authentic question types, chart-based Task 1, essay prompts and full speaking tests. Official samples link to the publisher." />
    <div className="panel panel-sun mb-8 p-6">
      <div className="flex items-center gap-2"><Sparkles className="text-sun" /><h2 className="section-title">Conjure a new task</h2></div>
      <p className="mt-2 font-read text-sm text-mist">{cloud ? `Cloud AI (${info?.model}) writes an original task; the Quality Manager checks it (e.g. every answer must appear in the script) before you can use it.` : 'The built-in engine creates writing and speaking tasks from your topic. Brand-new listening and reading tests need a cloud AI key — the bank already includes complete tests.'}</p>
      <div className="mt-4 grid gap-3 md:grid-cols-[150px_170px_1fr_auto]">
        <select aria-label="Skill to generate" className="input" value={genSkill} onChange={e => { setGenSkill(e.target.value); setTask('auto') }}>{['writing', 'speaking', 'listening', 'reading'].map(s => <option key={s} value={s}>{nice(s)}</option>)}</select>
        <select aria-label="Task type" className="input" value={task} onChange={e => setTask(e.target.value)}>{tasks[genSkill].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <input aria-label="Task topic" className="input" value={topic} maxLength={80} onChange={e => setTopic(e.target.value)} placeholder="Topic, e.g. space tourism" />
        <button className="btn-sun" onClick={generate} disabled={busy || topic.trim().length < 3 || needsCloud} title={needsCloud ? 'Needs a cloud AI key' : undefined}>{busy ? 'Conjuring…' : 'Generate'}<Sparkles size={16} /></button>
      </div>
    </div>
    <div className="mb-5 flex flex-wrap gap-1">{['all', 'listening', 'reading', 'writing', 'speaking'].map(s => <button key={s} className={skill === s ? 'btn-primary' : 'btn-secondary'} onClick={() => setSkill(s)}>{s === 'all' ? 'All skills' : nice(s)}</button>)}</div>
    {!items ? <Spinner /> : <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{items.filter(i => skill === 'all' || i.skill === skill).map(item => {
      const Icon = ICONS[item.skill] || BookOpen
      const [label, color] = SOURCE[item.source_kind] || [nice(item.source_kind), 'text-mist']
      return <article key={item.id} className="panel flex flex-col p-6" style={{ ['--edge' as any]: SKILL_COLOR[item.skill] + '99' }}>
        <div className="flex flex-wrap items-center gap-2"><Icon size={18} style={{ color: SKILL_COLOR[item.skill] }} /><span className="pill" style={{ color: SKILL_COLOR[item.skill] }}>{item.skill}</span><span className={`pill ${color}`}>{label}</span></div>
        <h2 className="heading mt-4 text-xl">{item.title}</h2>
        <p className="mt-1 font-pixel text-xs uppercase tracking-wider text-fog">{item.task_type} · {item.topic}</p>
        <p className="mt-3 line-clamp-4 flex-1 font-read text-sm leading-6 text-mist">{item.prompt || (item.source_kind === 'OFFICIAL_LINK' ? 'Opens the official sample page on the publisher site.' : 'Awaiting quality review.')}</p>
        <div className="mt-5">{item.source_url
          ? <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="btn-secondary w-full">Open official source <ExternalLink size={15} /></a>
          : <button onClick={() => start(item)} disabled={!item.available || item.exam !== profile?.exam} className="btn-primary w-full">{item.available ? 'Start practice' : 'Held for review'} <ArrowRight size={16} /></button>}</div>
      </article>
    })}</div>}
  </>
}

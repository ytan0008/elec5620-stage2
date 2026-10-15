import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Activity, AlertTriangle, ArrowRight, Gauge, MessageSquareWarning, BookMarked, BookOpen, GraduationCap, BrainCircuit, ChevronRight, ClipboardCheck, Clock3, FileText, Headphones, LayoutDashboard, Library, LogOut, Menu, Mic, Settings, ShieldCheck, Sparkles, Target, TrendingUp, UserRound, Wand2, X } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Health, NotebookStats, Persona, Plan, Profile, Result, User, health, post, put } from './api'
import { Empty, Metric, Notify, PageTitle, SKILL_COLOR, Spinner, Status, nice, skills, stamp, useLoad } from './ui'
import { PixelAvatar, personaName } from './pixel/Avatar'
import Scene from './pixel/Scene'
import { PersonaProvider, moodFor, usePersona } from './persona'
import { prefs, speak } from './voice'
import AuthPage from './AuthPage'
import OnboardingPage from './OnboardingPage'
import KnowledgeGraphPage from './KnowledgeGraphPage'
import QuestionBankPage from './QuestionBankPage'
import MockExamPage from './MockExamPage'
import PortraitPage from './PortraitPage'
import AgentChat from './AgentChat'
import ObjectivePractice from './exam/ObjectivePractice'
import WritingPractice from './exam/WritingPractice'
import SpeakingPage from './exam/SpeakingPage'
import TutorPage from './notebook/TutorPage'
import NotebookPage from './notebook/NotebookPage'
import SelectionCapture from './notebook/SelectionCapture'
import { AgentActivity, AgentMemoryPage, AnomaliesPage, DevOverview, ReportsPage } from './dev/DevConsole'
import { MyReports } from './ReportProblem'

const learnerNav = [['/dashboard', 'Overview', LayoutDashboard], ['/tutor', 'AI Tutor', GraduationCap], ['/notebook', 'Notebooks', BookMarked], ['/practice/listening', 'Listening', Headphones], ['/practice/reading', 'Reading', BookOpen], ['/practice/writing', 'Writing', FileText], ['/practice/speaking', 'Speaking', Mic],
  ['/mock', 'Mock examination', ClipboardCheck], ['/questions', 'Question bank', Library], ['/plans', 'Learning plan', Target], ['/analytics', 'Performance', TrendingUp], ['/materials', 'Study materials', BookOpen],
  ['/knowledge', 'Knowledge graph', BrainCircuit], ['/portrait', 'Learning portrait', UserRound], ['/profile', 'My profile', UserRound], ['/settings', 'Settings', Settings]] as const
const onboardingNav = [['/onboarding', 'Setup assistant', BrainCircuit], ['/settings', 'Settings', Settings]] as const
const instructorNav = [['/console', 'Developer console', Gauge], ['/workflow', 'Agent activity', Activity], ['/agent-memory', 'Agent memory', BrainCircuit], ['/anomalies', 'Anomalies', AlertTriangle], ['/reports', 'Learner reports', MessageSquareWarning], ['/instructor', 'Review queue', ShieldCheck], ['/quality', 'Quality operations', ClipboardCheck], ['/settings', 'Settings', Settings]] as const

function Logo() {
  return <span className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center bg-magenta text-night" style={{ boxShadow: '0 0 0 3px #140c2e, 4px 4px 0 3px #3ef0ff' }}><Wand2 size={20} /></span>
    <span className="font-arcade text-[13px] leading-5 text-moon">Certify<span className="text-cyan">AI</span><br /><span className="text-[8px] text-magenta">PIXEL ACADEMY</span></span></span>
}

function Shell({ user, onLogout, children, overlays }: { user: User; onLogout: () => void; children: React.ReactNode; overlays?: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const [info, setInfo] = useState<Health | null>(null)
  const { persona, aiSpeaking } = usePersona()
  const location = useLocation()
  useEffect(() => { health().then(setInfo).catch(() => {}) }, [])
  const nav = user.role === 'learner' ? (user.profile_complete === false ? onboardingNav : learnerNav) : instructorNav
  const home = user.role === 'learner' ? (user.profile_complete === false ? '/onboarding' : '/dashboard') : '/console'
  const developer = user.role === 'instructor'
  return <div className={`min-h-screen lg:flex ${developer ? 'dev-mode' : ''}`}>
    <aside className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col overflow-y-auto bg-abyss/95 p-5 transition-transform lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`} style={{ boxShadow: '4px 0 0 #2a1d5c' }}>
      <div className="flex items-center justify-between"><Link to={home} onClick={() => setOpen(false)}><Logo /></Link><button className="lg:hidden" aria-label="Close menu" onClick={() => setOpen(false)}><X /></button></div>
      <nav className="mt-8 flex-1 space-y-1">{nav.map(([path, label, Icon]) => <NavLink key={path} to={path} onClick={() => setOpen(false)}
        className={({ isActive }) => `flex items-center gap-3 px-3 py-2 font-pixel text-[15px] transition-colors ${isActive ? 'bg-magenta text-night' : 'text-mist hover:bg-plum hover:text-moon'}`}><Icon size={17} />{label}</NavLink>)}</nav>
      <div className="mt-4 border-t-4 border-plum pt-4">
        <div className="flex items-center gap-3"><PixelAvatar persona={persona} mood={moodFor(aiSpeaking, false, false)} size={40} /><div className="min-w-0"><p className="truncate font-pixel">{user.name}</p><p className="font-pixel text-xs uppercase text-fog">{nice(user.role)}</p></div></div>
        <button onClick={onLogout} className="btn-ghost mt-3"><LogOut size={15} /> Sign out</button>
      </div>
    </aside>
    {open && <button aria-label="Close menu overlay" className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={() => setOpen(false)} />}
    <main className="min-w-0 flex-1">
      <header className="flex h-16 items-center justify-between px-5 md:px-9">
        <button className="lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}><Menu /></button>
        <span className={`hidden font-pixel lg:block ${developer ? 'text-[#7dffb0]' : 'text-mist'}`}>{developer ? '> developer mode · teacher console_' : '✦ Your learning command centre'}</span>
        <Link to="/settings" className={`pill ${developer ? 'text-[#7dffb0]' : info?.mode === 'REAL' ? 'text-lime' : 'text-cyan'}`} title={info?.model}>{developer ? 'DEV · ' : ''}{info ? (info.mode === 'REAL' ? `Cloud AI · ${info.model}` : 'Built-in AI engine') : '…'}</Link>
      </header>
      <div key={location.pathname} className="anim-page mx-auto max-w-7xl px-5 pb-28 pt-2 md:px-9">{children}</div>
    </main>
    {overlays}
  </div>
}

function Dashboard({ user, notify }: { user: User; notify: Notify }) {
  const { persona, aiSpeaking } = usePersona()
  const profile = useLoad<Profile>('/profile')
  const plans = useLoad<Plan[]>('/plans')
  const analytics = useLoad<any>('/analytics')
  const tasks = useLoad<{ id: number; skill: string; title: string; complete: boolean }[]>('/tasks')
  const book = useLoad<NotebookStats>('/notebook/stats')
  const active = plans.data?.find(p => p.status === 'ACTIVE')
  const greeting = `Welcome back, ${user.name.split(' ')[0]}! Ready for today's quest? Your target is ${profile.data?.exam || 'your exam'} ${profile.data?.target_score ?? ''}.`
  const complete = async (id: number) => { try { await post(`/tasks/${id}/complete`); tasks.reload(); notify('Quest complete! +1 ✦') } catch (e) { notify((e as Error).message, 'error') } }
  const days = profile.data ? Math.max(0, Math.ceil((new Date(profile.data.exam_date).getTime() - Date.now()) / 86400000)) : null
  return <>
    <section className="panel panel-hot grid items-center gap-6 p-6 md:grid-cols-[auto_1fr] md:p-9">
      <button onClick={() => speak(greeting, persona, { force: true })} aria-label={`Hear ${personaName(persona)}`}><PixelAvatar persona={persona} mood={moodFor(aiSpeaking, false, false)} size={150} /></button>
      <div>
        <span className="eyebrow">Your learning realm</span>
        <h1 className="heading title-glow mt-3 text-3xl md:text-5xl">Good to see you, {user.name.split(' ')[0]}.</h1>
        <div className="tile mt-4 max-w-2xl font-read text-moon/90"><b className="font-pixel text-magenta">{personaName(persona)}:</b> {greeting}</div>
        <div className="mt-6 flex flex-wrap gap-2">
          <Link className="btn-primary" to={active ? '/practice/speaking' : '/plans'}>{active ? 'Speak with the examiner' : 'Create your plan'}<ArrowRight size={16} /></Link>
          <Link className="btn-cyan" to="/mock">Mock exam</Link>
          <Link className="btn-secondary" to="/analytics">View progress</Link>
        </div>
      </div>
    </section>
    <div className="stagger mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Metric label="Target" value={profile.data ? `${profile.data.exam} ${profile.data.target_score}` : '—'} icon={<Target />} color="#ff4fd8" />
      <Metric label="Days left" value={days === null ? '—' : String(days)} icon={<Clock3 />} color="#ffd34d" />
      <Metric label="Hours / week" value={`${profile.data?.weekly_hours ?? '—'}`} icon={<Sparkles />} color="#b8ff5c" />
      <Metric label="Verified results" value={String(analytics.data?.sample_count ?? 0)} icon={<ShieldCheck />} />
    </div>
    <div className="stagger mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{skills.map(skill => {
      const Icon = { listening: Headphones, reading: BookOpen, writing: FileText, speaking: Mic }[skill]!
      const score = analytics.data?.skill_scores?.[skill]
      return <Link key={skill} to={`/practice/${skill}`} className="panel group p-5 transition-transform hover:-translate-y-1" style={{ ['--edge' as any]: SKILL_COLOR[skill] }}>
        <div className="flex items-center justify-between"><Icon style={{ color: SKILL_COLOR[skill] }} /><span className="num text-4xl" style={{ color: SKILL_COLOR[skill] }}>{score ?? '—'}</span></div>
        <p className="mt-3 font-pixel text-xl">{nice(skill)}</p><p className="font-read text-xs text-fog">{score ? 'average verified estimate' : 'no verified result yet'}</p>
      </Link>
    })}</div>
    <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <div className="panel p-6">
        <div className="flex items-center justify-between"><h2 className="section-title">Today's quests</h2><Link to="/plans" className="btn-ghost">View plan <ChevronRight size={15} /></Link></div>
        {active ? <><p className="mt-2 font-read text-sm text-mist">{active.content?.rationale}</p>
          <div className="mt-4 space-y-3">{tasks.data?.filter(t => !t.complete).slice(0, 5).map(task => <div key={task.id} className="tile flex items-center justify-between gap-3">
            <div><span className="font-pixel text-xs uppercase" style={{ color: SKILL_COLOR[task.skill] }}>{task.skill}</span><p className="font-read">{task.title}</p></div>
            <div className="flex shrink-0 gap-1"><Link to={`/practice/${task.skill}`} className="btn-cyan !px-2 !py-1 text-xs">Go</Link><button onClick={() => complete(task.id)} className="btn-secondary !px-2 !py-1 text-xs">Done</button></div>
          </div>)}{tasks.data && !tasks.data.some(t => !t.complete) && <p className="font-pixel text-lime">All quests complete this week ✦</p>}</div></>
          : <Empty title="A plan is waiting to be made" body="Your Learning Coordinator turns your goals into weekly quests." action={<Link to="/plans" className="btn-primary">Generate plan</Link>} />}
      </div>
      <div className="panel p-6">
        <h2 className="section-title">Focus next</h2>
        <p className="mt-2 font-read text-sm text-mist">{analytics.data?.sample_count ? 'Your weakest verified skills.' : 'Starter suggestions from your profile.'}</p>
        <div className="mt-4 space-y-3">{(analytics.data?.weaknesses?.length ? analytics.data.weaknesses : profile.data?.priority_skills || ['writing']).map((skill: string) => <Link key={skill} to={`/practice/${skill}`} className="tile flex items-center justify-between font-pixel hover:bg-plum"><span>{nice(skill)} practice</span><ArrowRight size={16} /></Link>)}</div>
        <Link to="/materials" className="btn-ghost mt-4">Explore study materials →</Link>
      </div>
    </div>
    {book.data && <div className="panel panel-cyan mt-6 grid gap-4 p-6 md:grid-cols-[1fr_auto] md:items-center">
      <div><h2 className="section-title">Notebooks</h2>
        <p className="mt-2 font-read text-sm text-mist">{book.data.mistakes_by_type[0] ? <>You miss <b className="text-moon">{book.data.mistakes_by_type[0].name}</b> questions most ({book.data.mistakes_by_type[0].count}×). </> : 'Mistakes, unknown words and grammar slips are recorded automatically. '}
          {book.data.grammar_issues[0] && <>Top grammar slip: <b className="text-moon">{book.data.grammar_issues[0].name}</b>. </>}{book.data.due_words > 0 && <span className="text-cyan">{book.data.due_words} words due for review.</span>}</p></div>
      <div className="flex flex-wrap gap-2"><Link to="/notebook" className="btn-cyan">Open notebooks</Link><Link to="/tutor" className="btn-primary">Coach me</Link></div>
    </div>}
  </>
}

function ProfilePage({ notify }: { notify: Notify }) {
  const { data, setData, loading } = useLoad<Profile>('/profile')
  const [saving, setSaving] = useState(false)
  if (loading || !data) return <Spinner />
  const save = async (e: React.FormEvent) => { e.preventDefault(); setSaving(true); try { setData(await put('/profile', data)); notify('Profile saved') } catch (err) { notify((err as Error).message, 'error') } finally { setSaving(false) } }
  const update = (key: keyof Profile, value: any) => setData({ ...data, [key]: value })
  return <>
    <PageTitle eyebrow="Your foundation" title="Learner profile" subtitle="Keep your goals accurate so your plan, tests and question bank match your exam." />
    <form onSubmit={save} className="panel max-w-3xl p-6 md:p-8">
      <div className="grid gap-5 sm:grid-cols-2">
        <label><span className="label">Examination</span><select className="input" value={data.exam} onChange={e => setData({ ...data, exam: e.target.value as Profile['exam'], target_score: e.target.value === 'IELTS' ? 7 : 4.5 })}><option>IELTS</option><option>TOEFL</option></select></label>
        <label><span className="label">Current proficiency</span><select className="input" value={data.proficiency} onChange={e => update('proficiency', e.target.value)}><option>beginner</option><option>intermediate</option><option>advanced</option></select></label>
        <label><span className="label">Target · {data.exam === 'IELTS' ? '0–9 band' : '2026 1–6 scale'}</span><input className="input" type="number" min={data.exam === 'IELTS' ? 0 : 1} max={data.exam === 'IELTS' ? 9 : 6} step="0.5" value={data.target_score} onChange={e => update('target_score', Number(e.target.value))} /></label>
        <label><span className="label">Exam date</span><input className="input" type="date" value={data.exam_date} onChange={e => update('exam_date', e.target.value)} /></label>
        <label><span className="label">Study hours each week</span><input className="input" type="number" min="1" max="40" value={data.weekly_hours} onChange={e => update('weekly_hours', Number(e.target.value))} /></label>
      </div>
      <div className="mt-6"><span className="label">Priority skills</span><div className="flex flex-wrap gap-1">{skills.map(skill => <button type="button" key={skill} onClick={() => update('priority_skills', data.priority_skills.includes(skill) ? data.priority_skills.filter(s => s !== skill) : [...data.priority_skills, skill])} className={data.priority_skills.includes(skill) ? 'btn-primary' : 'btn-secondary'}>{nice(skill)}</button>)}</div></div>
      <button disabled={saving} className="btn-cyan mt-7">{saving ? 'Saving…' : 'Save profile'}</button>
    </form>
  </>
}

function PlansPage({ notify }: { notify: Notify }) {
  const { data, reload, loading } = useLoad<Plan[]>('/plans')
  const [busy, setBusy] = useState(false)
  const [changeText, setChangeText] = useState('')
  const act = async (fn: () => Promise<unknown>, message: string) => { setBusy(true); try { await fn(); reload(); notify(message) } catch (e) { notify((e as Error).message, 'error') } finally { setBusy(false) } }
  const active = data?.some(p => p.status === 'ACTIVE')
  return <>
    <PageTitle eyebrow="Learning coordinator" title="Your learning plan" subtitle="A weekly path shaped by your exam goal and verified progress."
      action={<button disabled={busy} onClick={() => act(() => post(`/plans/generate?adapt=${!!active}`), active ? 'Adapted plan proposed' : 'Plan generated')} className="btn-primary">{active ? 'Request adaptation' : 'Generate first plan'}<Sparkles size={16} /></button>} />
    {loading ? <Spinner /> : !data?.length ? <Empty title="No plan yet" body="Generate a personal plan from your confirmed profile." action={<button onClick={() => act(() => post('/plans/generate'), 'Plan generated')} className="btn-primary">Generate plan</button>} />
      : <div className="stagger space-y-5">{data.map(plan => <div className={`panel p-6 ${plan.status === 'ACTIVE' ? 'panel-lime' : ''}`} key={plan.id}>
        <div className="flex flex-wrap items-center justify-between gap-3"><div><span className="eyebrow">Version {plan.version} · {plan.kind}</span><h2 className="heading mt-2 text-2xl">{plan.content?.title || 'Plan in quality review'}</h2></div><Status value={plan.status} /></div>
        {plan.content ? <><p className="mt-4 font-read text-mist">{plan.content.rationale}</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">{plan.content.activities?.map((a: Record<string, any>, i: number) => <div key={i} className="tile"><span className="font-pixel text-xs uppercase" style={{ color: SKILL_COLOR[a.skill] }}>{a.skill} · {a.minutes_per_week} min / week</span><p className="mt-1 font-read">{a.title}</p><p className="mt-1 font-read text-xs text-fog">{a.reason}</p></div>)}</div>
          {plan.content.changes?.length > 0 && <p className="mt-4 font-read text-sm text-cyan">Changes: {plan.content.changes.join('; ')}</p>}</>
          : <p className="mt-4 font-read text-sun">Awaiting human quality review. The plan content is held.</p>}
        {plan.status === 'PROPOSED' && <div className="mt-5 space-y-3">
          <div className="flex flex-wrap gap-2"><button className="btn-lime" disabled={busy} onClick={() => act(() => post(`/plans/${plan.id}/decision?accept=true`), 'Plan activated')}>Accept plan</button><button className="btn-secondary" disabled={busy} onClick={() => act(() => post(`/plans/${plan.id}/decision?accept=false`), 'Proposal rejected; existing plan preserved')}>Reject</button></div>
          <div className="flex flex-wrap gap-2"><input className="input max-w-md" placeholder="Request a change, e.g. more speaking practice" value={changeText} onChange={e => setChangeText(e.target.value)} /><button className="btn-secondary" disabled={busy || changeText.trim().length < 5} onClick={() => act(async () => { await post(`/plans/${plan.id}/request-changes`, { note: changeText }); setChangeText('') }, 'Revised plan proposed')}>Request changes</button></div>
        </div>}
      </div>)}</div>}
  </>
}

const chartAxis = { stroke: '#b9b0e0', fontFamily: 'Pixelify Sans' }
function AnalyticsPage({ notify }: { notify: Notify }) {
  const { data, loading } = useLoad<any>('/analytics')
  const reports = useLoad<{ id: number; result: Result }[]>('/reports')
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState<Result | null>(null)
  const generate = async () => { setBusy(true); try { await post('/reports'); reports.reload(); notify('Verified report saved') } catch (e) { notify((e as Error).message, 'error') } finally { setBusy(false) } }
  if (loading || !data) return <Spinner />
  const max = data.exam === 'IELTS' ? 9 : 6
  return <>
    <PageTitle eyebrow="Performance intelligence" title="Your progress" subtitle="Estimates from verified practice and mock exams only." action={<button className="btn-primary" disabled={busy || !data.sample_count} onClick={generate}>Generate report</button>} />
    <div className="grid gap-4 md:grid-cols-3"><Metric label="Verified results" value={String(data.sample_count)} icon={<ShieldCheck />} /><Metric label="Target score" value={String(data.target_score)} icon={<Target />} color="#ff4fd8" /><Metric label="Readiness" value={data.readiness.replace('Estimated ', '')} icon={<TrendingUp />} color="#b8ff5c" /></div>
    {data.sample_count ? <div className="mt-6 grid gap-6 lg:grid-cols-2">
      <div className="panel p-6"><h2 className="section-title">Skill estimates</h2><div className="mt-5 h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={Object.entries(data.skill_scores).map(([skill, score]) => ({ skill, score }))}><CartesianGrid stroke="#3a2b7e" strokeDasharray="4 4" /><XAxis dataKey="skill" {...chartAxis} /><YAxis domain={[0, max]} {...chartAxis} /><Tooltip cursor={{ fill: 'rgba(107,82,214,.2)' }} /><Bar dataKey="score" fill="#ff4fd8" isAnimationActive={false} /></BarChart></ResponsiveContainer></div></div>
      <div className="panel p-6"><h2 className="section-title">Verified score history</h2><div className="mt-5 h-64"><ResponsiveContainer width="100%" height="100%"><LineChart data={data.history.map((h: any, i: number) => ({ ...h, index: i + 1 }))}><CartesianGrid stroke="#3a2b7e" strokeDasharray="4 4" /><XAxis dataKey="index" {...chartAxis} /><YAxis domain={[0, max]} {...chartAxis} /><Tooltip /><Line type="linear" dataKey="score" stroke="#3ef0ff" strokeWidth={3} dot={{ r: 4, fill: '#ffd34d', strokeWidth: 0 }} isAnimationActive={false} /></LineChart></ResponsiveContainer></div></div>
    </div> : <div className="mt-6"><Empty title="Insights need practice data" body="Complete a practice session before trends and weaknesses are estimated." action={<Link to="/practice/listening" className="btn-primary">Start listening practice</Link>} /></div>}
    <div className="mt-6 grid gap-6 lg:grid-cols-2">
      <div className="panel p-6"><h2 className="section-title">Areas to improve</h2><div className="mt-4 flex flex-wrap gap-2">{data.weaknesses?.length ? data.weaknesses.map((s: string) => <span key={s} className="pill text-sun">{nice(s)}</span>) : <span className="font-read text-mist">Not enough evidence yet.</span>}</div>
        {data.repeated_errors?.length > 0 && <div className="mt-4 space-y-1">{data.repeated_errors.map((r: any) => <p key={r.issue} className="font-read text-sm text-mist">▸ {r.issue} ×{r.count}</p>)}</div>}
        <div className="mt-5 space-y-2">{data.recommendations?.map((r: string) => <p key={r} className="tile font-read text-sm">{r}</p>)}</div></div>
      <div className="panel p-6"><h2 className="section-title">Saved reports</h2><div className="mt-4 space-y-2">{reports.data?.length ? reports.data.map(r => <button key={r.id} onClick={() => setOpen(r.result)} className="tile flex w-full items-center justify-between font-pixel"><span>Report #{r.id}</span><Status value={r.result.state} /></button>) : <p className="font-read text-mist">No saved reports yet.</p>}</div>
        {open?.payload && <div className="mt-4 tile font-read text-sm"><p>{open.payload.summary}</p>{open.payload.recommendations?.map((r: string) => <p key={r} className="mt-1 text-mist">▸ {r}</p>)}</div>}</div>
    </div>
  </>
}

function MaterialsPage({ notify }: { notify: Notify }) {
  const { data } = useLoad<any[]>('/materials')
  const [skill, setSkill] = useState('all')
  const [recommendations, setRecommendations] = useState<Result | null>(null)
  const [selected, setSelected] = useState<any>(null)
  const recommend = async () => { try { setRecommendations(await post('/materials/recommend')); notify('Recommendations quality checked') } catch (e) { notify((e as Error).message, 'error') } }
  const view = async (item: any) => { setSelected(item); try { await post(`/materials/${item.id}/interaction`) } catch (e) { notify((e as Error).message, 'error') } }
  const rate = async (relevant: boolean) => { if (!selected) return; try { await post(`/materials/${selected.id}/interaction?relevant=${relevant}`); notify('Thanks — relevance saved') } catch (e) { notify((e as Error).message, 'error') } }
  return <>
    <PageTitle eyebrow="Spellbook library" title="Study materials" subtitle="Strategy lessons for each skill and question type." action={<button onClick={recommend} className="btn-primary">Recommend for me<Sparkles size={16} /></button>} />
    {recommendations && <div className="panel panel-cyan mb-6 p-5"><div className="flex justify-between"><h2 className="section-title">Quality-checked recommendations</h2><Status value={recommendations.state} /></div>
      {recommendations.payload?.items ? <div className="mt-3 grid gap-3 md:grid-cols-2">{recommendations.payload.items.map((item: any) => <button key={item.id} onClick={() => view(data?.find(m => m.id === item.id))} className="tile text-left font-read text-sm"><b className="font-pixel text-base">{item.title}</b><br />{item.reason}</button>)}</div> : <p className="mt-3 font-read text-sun">Recommendations are held for review.</p>}</div>}
    <div className="mb-5 flex flex-wrap gap-1">{['all', ...skills].map(s => <button key={s} className={skill === s ? 'btn-primary' : 'btn-secondary'} onClick={() => setSkill(s)}>{nice(s)}</button>)}</div>
    <div key={skill} className="stagger grid gap-5 md:grid-cols-2 lg:grid-cols-3">{data?.filter(item => skill === 'all' || item.skill === skill).map(item => <button key={item.id} onClick={() => view(item)} className="panel p-6 text-left transition-transform hover:-translate-y-1" style={{ ['--edge' as any]: SKILL_COLOR[item.skill] + 'aa' }}>
      <span className="font-pixel text-xs uppercase" style={{ color: SKILL_COLOR[item.skill] }}>{item.exam} · {item.skill} · {item.level}</span><h3 className="heading mt-3 text-xl">{item.title}</h3><p className="mt-2 font-read text-sm text-mist">{item.description}</p><span className="btn-ghost mt-4 !px-0">Open lesson <ArrowRight size={14} /></span>
    </button>)}</div>
    {selected && createPortal(<div className="anim-fade fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-5" onClick={() => setSelected(null)}><div className="anim-pop panel panel-hot max-h-[85vh] w-full max-w-xl overflow-auto p-7" onClick={e => e.stopPropagation()} role="dialog" aria-label={selected.title}>
      <div className="flex justify-between"><span className="eyebrow">{selected.skill} lesson</span><button onClick={() => setSelected(null)} aria-label="Close lesson"><X /></button></div>
      <h2 className="heading mt-3 text-2xl">{selected.title}</h2><p className="reading mt-5 whitespace-pre-line">{selected.content}</p>
      <div className="mt-7 border-t-4 border-plum pt-5"><p className="mb-3 font-pixel">Was this relevant to your goal?</p><div className="flex gap-2"><button className="btn-lime" onClick={() => rate(true)}>Yes</button><button className="btn-secondary" onClick={() => rate(false)}>Not yet</button></div></div>
    </div></div>, document.body)}
  </>
}

function InstructorPage({ notify }: { notify: Notify }) {
  const { data, reload, loading } = useLoad<any[]>('/instructor/cases')
  const [selected, setSelected] = useState<any>(null)
  const [decision, setDecision] = useState('approve')
  const [note, setNote] = useState('')
  const [correction, setCorrection] = useState('')
  const submit = async () => {
    if (!selected) return
    try {
      let corrected: Record<string, any> | null = null
      if (decision === 'correct') { try { corrected = correction.trim().startsWith('{') ? JSON.parse(correction) : { summary: correction } } catch { notify('Correction JSON is invalid', 'error'); return } }
      await post(`/instructor/cases/${selected.id}/decision`, { decision, note, correction: corrected })
      notify('Decision recorded'); setSelected(null); reload()
    } catch (e) { notify((e as Error).message, 'error') }
  }
  return <>
    <PageTitle eyebrow="Human oversight" title="Instructor review queue" subtitle="Inspect held results and evidence before releasing a decision." action={<button onClick={reload} className="btn-secondary">Refresh queue</button>} />
    {loading ? <Spinner /> : !data?.length ? <Empty title="No escalations" body="Low-confidence or contradictory results will appear here." /> : <div className="grid gap-5 lg:grid-cols-[.75fr_1.25fr]">
      <div className="space-y-3">{data.map(item => <button key={item.id} className={`panel w-full p-5 text-left ${selected?.id === item.id ? 'panel-hot' : ''}`} onClick={() => { setSelected(item); setNote(''); setCorrection('') }}>
        <div className="flex justify-between"><span className="eyebrow">Case #{item.id}</span><Status value={item.status} /></div><p className="mt-3 font-pixel text-lg">{nice(item.package.kind)} result</p><p className="mt-1 line-clamp-2 font-read text-sm text-mist">{item.reason}</p></button>)}</div>
      {selected ? <div className="panel p-6">
        <div className="flex justify-between"><div><span className="eyebrow">Evidence review</span><h2 className="heading mt-2 text-2xl">Case #{selected.id}</h2></div><Status value={selected.status} /></div>
        <p className="tile mt-4 font-read text-sm text-sun">{selected.reason}</p>
        <div className="mt-5 grid gap-4 sm:grid-cols-2"><div><h3 className="font-pixel">AI output</h3><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap bg-abyss/80 p-4 font-terminal text-base">{JSON.stringify(selected.package.payload, null, 2)}</pre></div>
          <div><h3 className="font-pixel">Confidence and issues</h3><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap bg-abyss/80 p-4 font-terminal text-base">{JSON.stringify({ confidence: selected.package.confidence, issues: selected.package.issues, source: selected.package.source_mode }, null, 2)}</pre></div></div>
        {selected.decisions?.length > 0 && <div className="mt-5"><h3 className="font-pixel">Decision history</h3>{selected.decisions.map((d: any, i: number) => <p key={i} className="mt-2 font-read text-sm">{nice(d.decision)} — {d.note} · {stamp(d.created_at)}</p>)}</div>}
        {selected.status !== 'RESOLVED' && <div className="mt-6 border-t-4 border-plum pt-5"><h3 className="font-pixel">Instructor decision</h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-2"><select className="input" value={decision} onChange={e => setDecision(e.target.value)}><option value="approve">Approve AI result</option><option value="correct">Correct result</option><option value="request_information">Request more information</option></select><input className="input" placeholder="Decision note (required)" value={note} onChange={e => setNote(e.target.value)} /></div>
          {decision === 'correct' && <textarea className="input mt-3 min-h-24" placeholder="Corrected summary, or full JSON for incomplete results (required)" value={correction} onChange={e => setCorrection(e.target.value)} />}
          <button disabled={note.length < 3 || (decision === 'correct' && !correction.trim())} className="btn-primary mt-4" onClick={submit}>Record decision</button></div>}
      </div> : <Empty title="Select a case" body="Review evidence, confidence values and the AI output before deciding." />}
    </div>}
  </>
}

function QualityPage({ notify }: { notify: Notify }) {
  const { data, reload, loading } = useLoad<any>('/instructor/quality')
  const audit = useLoad<any[]>('/instructor/audit')
  const [threshold, setThreshold] = useState('0.70')
  useEffect(() => { if (data) setThreshold(String(data.threshold)) }, [data?.threshold])
  const saveThreshold = async () => { try { await put('/instructor/quality/threshold', { value: Number(threshold) }); reload(); audit.reload(); notify('Quality threshold updated') } catch (e) { notify((e as Error).message, 'error') } }
  if (loading || !data) return <Spinner />
  return <>
    <PageTitle eyebrow="Operations & quality" title="Quality control" subtitle="Every generated result passes structural, confidence and consistency checks." action={<button className="btn-secondary" onClick={() => { reload(); audit.reload() }}>Refresh</button>} />
    <div className="grid gap-4 md:grid-cols-3"><Metric label="Confidence threshold" value={String(data.threshold)} icon={<ShieldCheck />} /><Metric label="Pending review cases" value={String(data.pending)} icon={<Activity />} color="#ffd34d" /><Metric label="Recent checks" value={String(data.checks.length)} icon={<ClipboardCheck />} color="#b8ff5c" /></div>
    <div className="panel mt-6 flex flex-wrap items-end gap-3 p-5"><label><span className="label">Confidence threshold (0.50–0.95)</span><input className="input w-40" type="number" min="0.5" max="0.95" step="0.01" value={threshold} onChange={e => setThreshold(e.target.value)} /></label><button className="btn-primary" onClick={saveThreshold}>Save threshold</button><p className="font-read text-sm text-mist">Affects new checks; audit logged.</p></div>
    <div className="mt-6 grid gap-6 lg:grid-cols-2">
      <div className="panel p-6"><h2 className="section-title">Recent checks</h2><div className="mt-4 max-h-96 space-y-2 overflow-auto">{data.checks.map((c: any) => <div key={c.id} className="tile font-read text-sm"><div className="flex justify-between font-pixel"><b>Package #{c.package_id}</b><Status value={c.verdict} /></div><p className="mt-1 text-mist">{c.method} · {c.issues.join('; ') || 'No issues'}</p></div>)}</div></div>
      <div className="panel p-6"><h2 className="section-title">Audit trail</h2><div className="mt-4 max-h-96 space-y-2 overflow-auto">{audit.data?.map((row: any) => <div key={row.id} className="tile font-read text-sm"><b className="font-pixel">{nice(row.action)}</b><p className="text-mist">{stamp(row.created_at)} · {JSON.stringify(row.detail)}</p></div>)}</div></div>
    </div>
  </>
}

function SettingsPage({ user }: { user: User }) {
  const { persona, setPersona, aiSpeaking } = usePersona()
  const [info, setInfo] = useState<Health | null>(null)
  const [rate, setRate] = useState(prefs.rate)
  const [muted, setMuted] = useState(prefs.muted)
  useEffect(() => { health(true).then(setInfo).catch(() => {}) }, [])
  const choices: [Persona, string, string][] = [['witch', 'Luna the pixel witch', 'Warm, witty and a little magical.'], ['boy', 'Kai the pixel boy', 'Upbeat study buddy energy.']]
  return <>
    <PageTitle eyebrow="Workspace settings" title="Settings" subtitle="Choose your AI companion, tune the voice and check how the AI engine is configured." />
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="panel panel-hot p-6">
        <h2 className="section-title">AI companion</h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">{choices.map(([key, label, desc]) => <button key={key} onClick={() => setPersona(key)} aria-pressed={persona === key} className={`tile flex flex-col items-center gap-3 p-5 text-center ${persona === key ? 'tile-hot bg-plum' : ''}`}>
          <PixelAvatar persona={key} mood={persona === key ? moodFor(aiSpeaking, false, false) : 'idle'} size={110} /><span className="font-pixel text-lg">{label}</span><span className="font-read text-xs text-mist">{desc}</span>{persona === key && <span className="pill text-lime">Selected</span>}
        </button>)}</div>
        <div className="mt-6 space-y-4">
          <label className="block"><span className="label">Speaking speed · {rate.toFixed(2)}×</span><input type="range" min="0.7" max="1.3" step="0.05" value={rate} onChange={e => { const v = Number(e.target.value); setRate(v); prefs.rate = v }} className="w-full accent-magenta" /></label>
          <label className="flex items-center gap-3 font-pixel"><input type="checkbox" checked={!muted} onChange={e => { setMuted(!e.target.checked); prefs.muted = !e.target.checked }} className="h-5 w-5 accent-magenta" /> Speak chat replies aloud</label>
          <button className="btn-cyan" onClick={() => speak(`Hello ${user.name.split(' ')[0]}! I'm ${personaName(persona)}. Let's reach your target together.`, persona, { force: true })}>Test voice</button>
        </div>
      </div>
      <div className="space-y-6">
        <div className="panel p-6 space-y-4">
          <h2 className="section-title">Account</h2>
          <p className="font-read">{user.name} · {user.email}</p><p className="font-pixel text-sm text-mist">Role: {nice(user.role)}</p>
        </div>
        <div className="panel panel-cyan p-6 space-y-3">
          <h2 className="section-title">AI engine</h2>
          <p className="font-pixel"><span className={info?.mode === 'REAL' ? 'text-lime' : 'text-cyan'}>{info?.mode === 'REAL' ? `Cloud AI · ${info.model}` : 'Built-in engine'}</span></p>
          <p className="font-read text-sm text-mist">{info?.mode === 'REAL'
            ? 'A cloud language model writes conversation, examiner follow-ups, new tests and rubric feedback. Every result still passes the Quality Manager.'
            : 'Running fully offline: curated exam-format tests, rule-based rubric analysis and a scripted examiner. Add OPENAI_API_KEY (and optionally OPENAI_BASE_URL for an OpenAI-compatible provider) to .env and restart the backend for cloud AI.'}</p>
          <p className="font-read text-sm text-mist">Voice: {info?.server_tts ? 'cloud text-to-speech with high-quality voices' : 'your browser’s built-in voices (Edge “Natural” voices sound best)'}. Speech input: browser recognition{info?.server_stt ? ' + cloud transcription' : ''}.</p>
        </div>
        {user.role === 'learner' && <MyReports />}
        <div className="panel panel-flat p-6"><h2 className="section-title">Quality policy</h2><p className="mt-2 font-read text-sm text-mist">Results stay held when confidence is under the threshold (default 0.70) or feedback conflicts with scores. An instructor can resolve held cases. Scores are unofficial estimates.</p></div>
      </div>
    </div>
  </>
}

function PracticeRoute({ notify }: { notify: Notify }) {
  const { skill = 'writing' } = useParams()
  const location = useLocation()
  const question = new URLSearchParams(location.search).get('question') || ''
  if (skill === 'listening' || skill === 'reading') return <ObjectivePractice key={skill + question} skill={skill} notify={notify} />
  if (skill === 'writing') return <WritingPractice key={question} notify={notify} />
  if (skill === 'speaking') return <SpeakingPage key={question} notify={notify} />
  return <Navigate to="/dashboard" />
}

function AppInner() {
  const [user, setUser] = useState<User | null>(() => { try { return JSON.parse(localStorage.getItem('certifyai_user') || 'null') } catch { return null } })
  const [toast, setToast] = useState<{ message: string; kind: string } | null>(null)
  const navigate = useNavigate()
  const notify: Notify = (message, kind = 'success') => { setToast({ message, kind }); window.setTimeout(() => setToast(null), 5000) }
  const store = (u: User) => { localStorage.setItem('certifyai_user', JSON.stringify(u)); setUser(u) }
  const auth = (u: User, token: string) => { localStorage.setItem('certifyai_token', token); store(u); navigate(u.role === 'learner' ? (u.profile_complete === false ? '/onboarding' : '/dashboard') : '/console') }
  const markProfileComplete = () => setUser(previous => { if (!previous) return previous; const updated = { ...previous, profile_complete: true }; localStorage.setItem('certifyai_user', JSON.stringify(updated)); return updated })
  const logout = () => { ['certifyai_token', 'certifyai_user', 'last-listening', 'last-reading', 'last-writing'].forEach(key => localStorage.removeItem(key)); setUser(null); navigate('/') }
  const home = user ? (user.role === 'learner' ? (user.profile_complete === false ? '/onboarding' : '/dashboard') : '/console') : '/'
  return <div className="scanlines">
    <Scene />
    {user ? <PersonaProvider initial={user.avatar || 'witch'} onChange={avatar => store({ ...user, avatar })}>
      <Shell user={user} onLogout={logout} overlays={user.role === 'learner' && user.profile_complete !== false ? <><AgentChat /><SelectionCapture notify={notify} /></> : null}><Routes>
        {user.role === 'learner' ? (user.profile_complete === false
          ? <Route path="/onboarding" element={<OnboardingPage onComplete={markProfileComplete} notify={notify} />} />
          : <>
            <Route path="/onboarding" element={<OnboardingPage onComplete={markProfileComplete} notify={notify} />} />
            <Route path="/dashboard" element={<Dashboard user={user} notify={notify} />} />
            <Route path="/profile" element={<ProfilePage notify={notify} />} />
            <Route path="/plans" element={<PlansPage notify={notify} />} />
            <Route path="/practice/:skill" element={<PracticeRoute notify={notify} />} />
            <Route path="/mock" element={<MockExamPage notify={notify} />} />
            <Route path="/questions" element={<QuestionBankPage notify={notify} />} />
            <Route path="/knowledge" element={<KnowledgeGraphPage />} />
            <Route path="/portrait" element={<PortraitPage />} />
            <Route path="/analytics" element={<AnalyticsPage notify={notify} />} />
            <Route path="/materials" element={<MaterialsPage notify={notify} />} />
            <Route path="/tutor" element={<TutorPage notify={notify} />} />
            <Route path="/notebook" element={<NotebookPage notify={notify} />} />
          </>) : <>
          <Route path="/console" element={<DevOverview />} />
          <Route path="/workflow" element={<AgentActivity />} />
          <Route path="/agent-memory" element={<AgentMemoryPage />} />
          <Route path="/anomalies" element={<AnomaliesPage notify={notify} />} />
          <Route path="/reports" element={<ReportsPage notify={notify} />} />
          <Route path="/instructor" element={<InstructorPage notify={notify} />} />
          <Route path="/quality" element={<QualityPage notify={notify} />} />
        </>}
        <Route path="/settings" element={<SettingsPage user={user} />} />
        <Route path="*" element={<Navigate to={home} />} />
      </Routes></Shell>
    </PersonaProvider> : <Routes><Route path="*" element={<AuthPage onAuth={auth} notify={notify} />} /></Routes>}
    {toast && <div key={toast.message} role="status" className={`panel toast-in fixed bottom-24 left-1/2 z-[80] max-w-md -translate-x-1/2 px-5 py-3 font-pixel ${toast.kind === 'error' ? 'panel-hot text-rose' : 'panel-lime text-lime'}`}>{toast.message}</div>}
  </div>
}

export default function App() { return <BrowserRouter><AppInner /></BrowserRouter> }

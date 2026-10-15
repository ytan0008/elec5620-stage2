import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, AlertTriangle, Bell, CheckCircle2, Cpu, MessageSquareWarning, Pause, Play, RefreshCw, ShieldCheck, Users } from 'lucide-react'
import { post } from '../api'
import { Empty, Metric, Notify, PageTitle, Spinner, Status, nice, stamp, useLoad } from '../ui'

type Overview = { mode: string; model: string; events_24h: number; events_7d: number; results_7d: number; held_7d: number; hold_rate: number; learners: number; active_learners_7d: number; open_reports: number;
  agents: { agent: string; events: number; avg_ms: number; p95_ms: number; slow: number }[]; timeline: { hour: string; events: number }[]; workflows: { workflow: string; count: number }[] }
type Anomaly = { id: string; severity: 'high' | 'medium' | 'low'; category: string; title: string; detail: string; time: string; user: string; email: string; ref: Record<string, any>; acknowledged: boolean }
type AgentEvent = { id: number; user_id: number; user: string; email: string; workflow: string; agent: string; phase: string; detail: Record<string, any>; mode: string; duration_ms: number; created_at: string }
type Report = { id: number; category: string; message: string; context: Record<string, any>; status: string; response: string | null; created_at: string; resolved_at: string | null; user: string; email: string }

const SEVERITY: Record<string, string> = { high: '#ff6b8b', medium: '#ffd34d', low: '#3ef0ff' }
const AGENT_COLOR: Record<string, string> = { 'Learning Coordinator': '#b8ff5c', 'AI Tutor': '#ff4fd8', 'Assessment & Analytics': '#ffd34d', 'Quality Manager': '#3ef0ff', 'Human Instructor': '#ff8a3d', Learner: '#9b8cff' }
const axis = { stroke: '#7dffb0', fontFamily: 'VT323', fontSize: 15 }

function SeverityBadge({ value }: { value: string }) {
  return <span className="pill" style={{ color: SEVERITY[value] }}>{value}</span>
}

function useAutoRefresh(reload: () => void, ms: number, on = true) {
  useEffect(() => { if (!on) return; const id = window.setInterval(reload, ms); return () => window.clearInterval(id) }, [on])
}

/* ---------------- overview ---------------- */
export function DevOverview() {
  const overview = useLoad<Overview>('/instructor/overview')
  const anomalies = useLoad<Anomaly[]>('/instructor/anomalies')
  useAutoRefresh(() => { overview.reload(); anomalies.reload() }, 10000)
  const data = overview.data
  if (!data) return <Spinner label="Booting developer console…" />
  const open = (anomalies.data || []).filter(a => !a.acknowledged)
  return <>
    <PageTitle eyebrow="Developer mode · system health" title="Developer console" subtitle={`Engine: ${data.mode === 'REAL' ? `cloud AI (${data.model})` : 'built-in local engine'}. Live metrics refresh every 10 seconds.`}
      action={<button className="btn-secondary" onClick={() => { overview.reload(); anomalies.reload() }}><RefreshCw size={15} /> Refresh</button>} />
    <div className="stagger grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Metric label="Agent events · 24h" value={String(data.events_24h)} icon={<Activity />} color="#7dffb0" />
      <Metric label="Hold rate · 7d" value={`${Math.round(data.hold_rate * 100)}%`} icon={<ShieldCheck />} color={data.hold_rate > .3 ? '#ff6b8b' : '#ffd34d'} />
      <Metric label="Open anomalies" value={String(open.length)} icon={<AlertTriangle />} color={open.some(a => a.severity === 'high') ? '#ff6b8b' : '#3ef0ff'} />
      <Metric label="Active learners · 7d" value={`${data.active_learners_7d}/${data.learners}`} icon={<Users />} color="#ff4fd8" />
    </div>
    <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <div className="panel panel-term p-6"><h2 className="section-title">Agent events · last 24 hours</h2>
        <div className="mt-4 h-60"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data.timeline}>
          <defs><linearGradient id="evt" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#7dffb0" stopOpacity={.6} /><stop offset="100%" stopColor="#7dffb0" stopOpacity={0} /></linearGradient></defs>
          <CartesianGrid stroke="#1f4a3a" strokeDasharray="4 4" /><XAxis dataKey="hour" {...axis} interval={3} /><YAxis allowDecimals={false} {...axis} /><Tooltip />
          <Area type="stepAfter" dataKey="events" stroke="#7dffb0" strokeWidth={2} fill="url(#evt)" isAnimationActive={false} /></AreaChart></ResponsiveContainer></div></div>
      <div className="panel panel-term p-6"><h2 className="section-title">Workflow mix · 7d</h2>
        <div className="mt-4 h-60"><ResponsiveContainer width="100%" height="100%"><BarChart data={data.workflows.slice(0, 8)} layout="vertical" margin={{ left: 20 }}>
          <CartesianGrid stroke="#1f4a3a" strokeDasharray="4 4" /><XAxis type="number" allowDecimals={false} {...axis} /><YAxis type="category" dataKey="workflow" width={95} {...axis} /><Tooltip cursor={{ fill: 'rgba(125,255,176,.08)' }} />
          <Bar dataKey="count" fill="#3ef0ff" isAnimationActive={false} /></BarChart></ResponsiveContainer></div></div>
    </div>
    <div className="mt-6 grid gap-6 lg:grid-cols-2">
      <div className="panel panel-term p-6"><h2 className="flex items-center gap-2 section-title"><Cpu size={18} className="text-[#7dffb0]" /> Agent performance · 7d</h2>
        <table className="mt-4 w-full font-terminal text-lg"><thead><tr className="text-left text-[#7dffb0]"><th>Agent</th><th className="text-right">Events</th><th className="text-right">Avg</th><th className="text-right">p95</th><th className="text-right">Slow</th></tr></thead>
          <tbody>{data.agents.map(a => <tr key={a.agent} className="border-t border-[#1f4a3a]"><td style={{ color: AGENT_COLOR[a.agent] || '#f4ecff' }}>{a.agent}</td><td className="text-right">{a.events}</td><td className="text-right">{a.avg_ms}ms</td><td className="text-right">{a.p95_ms}ms</td><td className={`text-right ${a.slow ? 'text-rose' : 'text-fog'}`}>{a.slow}</td></tr>)}</tbody></table>
        <Link to="/workflow" className="btn-ghost mt-3 !px-0">Open live agent trace →</Link></div>
      <div className="panel panel-term p-6"><h2 className="flex items-center gap-2 section-title"><Bell size={18} className="text-rose" /> Latest anomalies</h2>
        <div className="stagger mt-4 space-y-2">{open.slice(0, 6).map(a => <div key={a.id} className="tile flex items-start gap-3 font-read text-sm"><SeverityBadge value={a.severity} /><div className="min-w-0"><p className="font-pixel">{a.title}</p><p className="truncate text-fog">{a.user} · {stamp(a.time)}</p></div></div>)}
          {!open.length && <p className="flex items-center gap-2 font-pixel text-lime"><CheckCircle2 size={16} /> All clear — no open anomalies</p>}</div>
        <div className="mt-3 flex gap-3"><Link to="/anomalies" className="btn-ghost !px-0">All anomalies →</Link><Link to="/reports" className="btn-ghost !px-0">{data.open_reports} open learner report{data.open_reports === 1 ? '' : 's'} →</Link></div></div>
    </div>
  </>
}

/* ---------------- agent activity ---------------- */
export function AgentActivity() {
  const [agent, setAgent] = useState('')
  const [learnerFilter, setLearnerFilter] = useState('')
  const [slow, setSlow] = useState(false)
  const [live, setLive] = useState(true)
  const [open, setOpen] = useState<number | null>(null)
  const query = `/events?limit=200${agent ? `&agent=${encodeURIComponent(agent)}` : ''}${slow ? '&slow=true' : ''}`
  const { data, loading, reload } = useLoad<AgentEvent[]>(query, [query])
  useEffect(() => { if (!live) return; const id = window.setInterval(reload, 4000); return () => window.clearInterval(id) }, [live, query])
  const shown = (data || []).filter(e => !learnerFilter || `${e.user} ${e.email}`.toLowerCase().includes(learnerFilter.toLowerCase()))
  return <>
    <PageTitle eyebrow="Developer mode · live trace" title="Agent activity" subtitle="Every perception, decision, handoff, quality check and release, across all learners." action={<button className={live ? 'btn-lime' : 'btn-secondary'} onClick={() => setLive(!live)}>{live ? <><Pause size={15} /> Live</> : <><Play size={15} /> Paused</>}</button>} />
    <div className="panel panel-term mb-5 flex flex-wrap items-center gap-3 p-4">
      <select aria-label="Agent filter" className="input !w-56" value={agent} onChange={e => setAgent(e.target.value)}><option value="">All agents</option>{Object.keys(AGENT_COLOR).map(a => <option key={a}>{a}</option>)}</select>
      <input aria-label="Learner filter" className="input !w-64" placeholder="Filter by learner name or email" value={learnerFilter} onChange={e => setLearnerFilter(e.target.value)} />
      <label className="flex items-center gap-2 font-pixel text-sm"><input type="checkbox" checked={slow} onChange={e => setSlow(e.target.checked)} className="accent-magenta" /> Slow steps only</label>
      <span className="ml-auto font-terminal text-lg text-[#7dffb0]">{shown.length} events{live && <span className="ml-2 inline-block h-2 w-2 animate-pulse bg-[#7dffb0]" />}</span>
    </div>
    {loading && !data ? <Spinner /> : !shown.length ? <Empty title="No matching agent events" body="Activity appears as learners use the platform." /> : <div className="panel panel-term p-4 md:p-6">
      <div className="space-y-2">{shown.map(event => <div key={event.id} className="anim-slide">
        <button onClick={() => setOpen(open === event.id ? null : event.id)} className="tile flex w-full flex-wrap items-center gap-3 text-left font-terminal text-lg hover:bg-plum">
          <span className="w-16 text-fog">#{event.id}</span>
          <span className="w-44 truncate" style={{ color: AGENT_COLOR[event.agent] || '#f4ecff' }}>{event.agent}</span>
          <span className="pill !text-[10px] text-cyan">{nice(event.phase)}</span>
          <span className="text-mist">{nice(event.workflow)}</span>
          <span className="min-w-0 flex-1 truncate text-moon/80">{event.user || '—'} <span className="text-fog">{event.email}</span></span>
          <span className={event.duration_ms > 8000 ? 'text-rose' : 'text-fog'}>{event.duration_ms}ms</span>
          <span className="text-fog">{new Date(event.created_at).toLocaleTimeString()}</span>
        </button>
        {open === event.id && <pre className="anim-fade mt-1 overflow-auto whitespace-pre-wrap bg-abyss/90 p-3 font-terminal text-base text-[#7dffb0]">{JSON.stringify({ mode: event.mode, at: event.created_at, ...event.detail }, null, 2)}</pre>}
      </div>)}</div>
    </div>}
  </>
}

/* ---------------- anomalies ---------------- */
export function AnomaliesPage({ notify }: { notify: Notify }) {
  const { data, loading, reload, setData } = useLoad<Anomaly[]>('/instructor/anomalies')
  const [severity, setSeverity] = useState('all')
  const [category, setCategory] = useState('all')
  const [showAck, setShowAck] = useState(false)
  useAutoRefresh(reload, 15000)
  const categories = useMemo(() => Array.from(new Set((data || []).map(a => a.category))), [data])
  const shown = (data || []).filter(a => (showAck || !a.acknowledged) && (severity === 'all' || a.severity === severity) && (category === 'all' || a.category === category))
  const ack = async (item: Anomaly) => {
    try { await post('/instructor/anomalies/ack', { anomaly_id: item.id }); setData(previous => (previous || []).map(a => a.id === item.id ? { ...a, acknowledged: true } : a)); notify('Anomaly acknowledged') } catch (e) { notify((e as Error).message, 'error') }
  }
  const counts = (data || []).filter(a => !a.acknowledged).reduce<Record<string, number>>((acc, a) => ({ ...acc, [a.severity]: (acc[a.severity] || 0) + 1 }), {})
  return <>
    <PageTitle eyebrow="Developer mode · anomaly detection" title="Anomalies" subtitle="Model failures, provider outages, quality holds, latency spikes, score inconsistencies, curriculum gaps, inactivity and learner reports — detected from stored evidence."
      action={<button className="btn-secondary" onClick={reload}><RefreshCw size={15} /> Rescan</button>} />
    <div className="stagger mb-5 grid gap-4 sm:grid-cols-3">{(['high', 'medium', 'low'] as const).map(level => <button key={level} onClick={() => setSeverity(severity === level ? 'all' : level)} className={`panel panel-flat p-4 text-left ${severity === level ? 'panel-hot' : ''}`}>
      <p className="font-pixel uppercase" style={{ color: SEVERITY[level] }}>{level}</p><p className="num text-5xl" style={{ color: SEVERITY[level] }}>{counts[level] || 0}</p></button>)}</div>
    <div className="mb-5 flex flex-wrap items-center gap-2">
      <select aria-label="Category" className="input !w-60" value={category} onChange={e => setCategory(e.target.value)}><option value="all">All categories</option>{categories.map(c => <option key={c}>{c}</option>)}</select>
      <label className="flex items-center gap-2 font-pixel text-sm"><input type="checkbox" checked={showAck} onChange={e => setShowAck(e.target.checked)} className="accent-magenta" /> Show acknowledged</label>
    </div>
    {loading && !data ? <Spinner /> : !shown.length ? <Empty title="No anomalies" body="The system looks healthy for the selected filters." /> : <div className="stagger space-y-3">{shown.map(item => <article key={item.id} className={`panel p-5 ${item.acknowledged ? 'opacity-60' : ''}`} style={{ ['--edge' as any]: SEVERITY[item.severity] }}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><SeverityBadge value={item.severity} /><span className="font-pixel text-xs uppercase text-mist">{item.category}</span></div>
          <h3 className="mt-2 font-pixel text-lg">{item.title}</h3><p className="mt-1 font-read text-sm text-mist">{item.detail}</p>
          <p className="mt-2 font-read text-xs text-fog">{item.user}{item.email ? ` · ${item.email}` : ''} · {stamp(item.time)}</p></div>
        <div className="flex flex-col items-end gap-2">
          {item.acknowledged ? <span className="pill text-lime">acknowledged</span> : <button className="btn-secondary !py-1 text-xs" onClick={() => ack(item)}>Acknowledge</button>}
          {item.ref?.package_id && <Link to="/instructor" className="btn-ghost text-xs">Review queue →</Link>}
          {item.ref?.report_id && <Link to="/reports" className="btn-ghost text-xs">Open report →</Link>}
        </div>
      </div>
    </article>)}</div>}
  </>
}

/* ---------------- learner reports ---------------- */
export function ReportsPage({ notify }: { notify: Notify }) {
  const { data, loading, reload } = useLoad<Report[]>('/instructor/feedback')
  const [status, setStatus] = useState('OPEN')
  const [reply, setReply] = useState<Record<number, string>>({})
  const resolve = async (report: Report) => {
    try { await post(`/instructor/feedback/${report.id}/resolve`, { response: reply[report.id] }); notify('Reply sent to the learner'); reload() } catch (e) { notify((e as Error).message, 'error') }
  }
  const shown = (data || []).filter(r => status === 'ALL' || r.status === status)
  return <>
    <PageTitle eyebrow="Developer mode · feedback" title="Learner reports" subtitle="Problems learners flagged on results, questions, the tutor or audio. Replies appear in the learner's Settings page." />
    <div className="mb-5 flex gap-1">{['OPEN', 'RESOLVED', 'ALL'].map(s => <button key={s} className={status === s ? 'btn-primary' : 'btn-secondary'} onClick={() => setStatus(s)}>{nice(s)}</button>)}</div>
    {loading && !data ? <Spinner /> : !shown.length ? <Empty title="No reports" body="Learners can report a problem from any result, the tutor or Settings." /> : <div className="stagger space-y-3">{shown.map(report => <article key={report.id} className="panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2"><MessageSquareWarning size={17} className="text-sun" /><span className="font-pixel">{report.user}</span><span className="font-read text-xs text-fog">{report.email} · {stamp(report.created_at)}</span></div><div className="flex gap-2"><span className="pill text-cyan">{report.category}</span><Status value={report.status} /></div></div>
      <p className="mt-3 font-read">{report.message}</p>
      {Object.keys(report.context || {}).length > 0 && <p className="mt-2 font-terminal text-base text-fog">{Object.entries(report.context).map(([k, v]) => `${k}: ${v}`).join(' · ')}</p>}
      {report.status === 'RESOLVED' ? <p className="tile mt-3 font-read text-sm text-lime">Reply: {report.response}</p>
        : <form className="mt-3 flex gap-2" onSubmit={e => { e.preventDefault(); void resolve(report) }}><input aria-label="Reply" className="input" placeholder="Reply to the learner and resolve" value={reply[report.id] || ''} onChange={e => setReply({ ...reply, [report.id]: e.target.value })} /><button className="btn-cyan" disabled={(reply[report.id] || '').trim().length < 3}>Resolve</button></form>}
    </article>)}</div>}
  </>
}


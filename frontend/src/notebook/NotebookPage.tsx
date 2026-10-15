import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { BookMarked, Check, Eye, Plus, RotateCcw, Trash2, Volume2, X } from 'lucide-react'
import { NotebookEntry, NotebookKind, NotebookStats, askTutor, post, request } from '../api'
import { usePersona } from '../persona'
import { speak } from '../voice'
import { Empty, Notify, PageTitle, SKILL_COLOR, Spinner, nice } from '../ui'

type Tab = 'overview' | NotebookKind
const TABS: [Tab, string][] = [['overview', 'Overview'], ['mistake', 'Mistake book'], ['word', 'Word book'], ['grammar', 'Grammar book'], ['sentence', 'Sentence book']]
const COLORS = ['#ff4fd8', '#3ef0ff', '#ffd34d', '#b8ff5c', '#ff8a3d', '#9b8cff']
const axis = { stroke: '#b9b0e0', fontFamily: 'Pixelify Sans', fontSize: 12 }

function useEntries(kind: NotebookKind | null) {
  const [entries, setEntries] = useState<NotebookEntry[] | null>(null)
  const reload = () => { if (kind) request<NotebookEntry[]>(`/notebook?kind=${kind}`).then(setEntries).catch(() => setEntries([])) }
  useEffect(() => { setEntries(null); reload() }, [kind])
  useEffect(() => { const on = () => reload(); window.addEventListener('notebook-changed', on); return () => window.removeEventListener('notebook-changed', on) }, [kind])
  return { entries, setEntries, reload }
}

function EntryActions({ entry, onChange, notify }: { entry: NotebookEntry; onChange: (entry: NotebookEntry | null) => void; notify: Notify }) {
  const toggle = async () => { try { onChange(await request<NotebookEntry>(`/notebook/${entry.id}`, { method: 'PATCH', body: JSON.stringify({ mastered: !entry.mastered }) })) } catch (e) { notify((e as Error).message, 'error') } }
  const remove = async () => { try { await request(`/notebook/${entry.id}`, { method: 'DELETE' }); onChange(null) } catch (e) { notify((e as Error).message, 'error') } }
  return <div className="flex items-center gap-1">
    <button onClick={toggle} className={`pill ${entry.mastered ? 'text-lime' : 'text-mist'}`} aria-pressed={entry.mastered}>{entry.mastered ? <><Check size={12} /> mastered</> : 'mark mastered'}</button>
    <button onClick={remove} aria-label="Delete entry" className="p-1 text-fog hover:text-rose"><Trash2 size={15} /></button>
  </div>
}

function Meta({ entry }: { entry: NotebookEntry }) {
  return <div className="flex flex-wrap items-center gap-2 font-pixel text-xs uppercase">
    {entry.skill && <span style={{ color: SKILL_COLOR[entry.skill] || '#b9b0e0' }}>{entry.skill}</span>}
    {entry.category && <span className="text-sun">{entry.category}</span>}
    {entry.count > 1 && <span className="pill text-rose">×{entry.count}</span>}
    <span className="normal-case text-fog">{entry.source}</span>
  </div>
}

/* ---------------- overview ---------------- */
function Overview({ stats, go }: { stats: NotebookStats; go: (tab: Tab) => void }) {
  const tiles: [NotebookKind, string, string][] = [['mistake', 'Mistakes', '#ff4fd8'], ['word', 'Words', '#3ef0ff'], ['grammar', 'Grammar slips', '#ffd34d'], ['sentence', 'Sentences', '#b8ff5c']]
  return <div className="space-y-6">
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{tiles.map(([kind, label, color]) => <button key={kind} onClick={() => go(kind)} className="panel panel-flat p-5 text-left" style={{ ['--edge' as any]: color }}>
      <p className="font-pixel text-sm uppercase tracking-wider text-mist">{label}</p>
      <p className="num mt-2 text-5xl" style={{ color }}>{stats.counts[kind]?.active ?? 0}</p>
      <p className="font-read text-xs text-fog">{stats.counts[kind]?.mastered ?? 0} mastered</p>
    </button>)}</div>
    {(stats.due_words > 0 || stats.due_mistakes > 0) && <div className="panel panel-sun flex flex-wrap items-center justify-between gap-3 p-5">
      <p className="font-pixel text-lg">Due for review: <span className="text-cyan">{stats.due_words} words</span> · <span className="text-magenta">{stats.due_mistakes} mistakes</span></p>
      <div className="flex gap-2">{stats.due_words > 0 && <button className="btn-cyan" onClick={() => go('word')}>Review words</button>}{stats.due_mistakes > 0 && <button className="btn-primary" onClick={() => go('mistake')}>Retry mistakes</button>}</div>
    </div>}
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="panel p-6"><h2 className="section-title">Which question types I miss most</h2>
        {stats.mistakes_by_type.length ? <div className="mt-4 h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={stats.mistakes_by_type} layout="vertical" margin={{ left: 30 }}>
          <CartesianGrid stroke="#3a2b7e" strokeDasharray="4 4" /><XAxis type="number" allowDecimals={false} {...axis} /><YAxis type="category" dataKey="name" width={150} {...axis} /><Tooltip cursor={{ fill: 'rgba(107,82,214,.2)' }} />
          <Bar dataKey="count" isAnimationActive={false}>{stats.mistakes_by_type.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Bar></BarChart></ResponsiveContainer></div>
          : <p className="mt-3 font-read text-mist">No mistakes recorded yet. Wrong listening and reading answers appear here automatically.</p>}</div>
      <div className="panel p-6"><h2 className="section-title">Mistakes by skill</h2>
        <div className="mt-4 space-y-3">{stats.mistakes_by_skill.length ? stats.mistakes_by_skill.map(item => <div key={item.name}>
          <div className="flex justify-between font-pixel"><span style={{ color: SKILL_COLOR[item.name] }}>{nice(item.name)}</span><span className="num text-2xl">{item.count}</span></div>
          <div className="bar mt-1"><span style={{ width: `${item.count / stats.mistakes_by_skill[0].count * 100}%`, background: SKILL_COLOR[item.name] }} /></div>
        </div>) : <p className="font-read text-mist">—</p>}</div>
        <h2 className="section-title mt-6">Most repeated grammar slips</h2>
        <ol className="mt-3 space-y-1 font-read">{stats.grammar_issues.length ? stats.grammar_issues.map((item, i) => <li key={item.name} className="flex justify-between gap-3"><span><b className="font-terminal text-xl text-sun">{i + 1}.</b> {item.name}</span><span className="pill text-rose">×{item.count}</span></li>) : <li className="text-mist">Grammar errors from your writing and speaking feedback appear here.</li>}</ol>
      </div>
    </div>
    <div className="panel panel-flat p-5 font-read text-sm text-mist"><b className="font-pixel text-moon">Tip:</b> select any word or sentence on any page — passages, transcripts, feedback, chat — and press <b className="text-magenta">Word book</b> or <b className="text-cyan">Sentence book</b>. You can also tell the AI tutor “I don't know the word …”.</div>
  </div>
}

/* ---------------- mistakes ---------------- */
function MistakeCard({ entry, onChange, notify }: { entry: NotebookEntry; onChange: (e: NotebookEntry | null) => void; notify: Notify }) {
  const d = entry.detail
  const [answer, setAnswer] = useState('')
  const [result, setResult] = useState<boolean | null>(null)
  const [reveal, setReveal] = useState(false)
  const choice = ['mcq', 'matching', 'tfng', 'ynng'].includes(d.type)
  const retry = async (value = answer) => {
    if (!value.trim()) return
    try { const r = await post<{ correct: boolean; entry: NotebookEntry }>(`/notebook/${entry.id}/retry`, { answer: value }); setResult(r.correct); onChange(r.entry); if (r.correct) setReveal(true) } catch (e) { notify((e as Error).message, 'error') }
  }
  return <article className={`panel p-5 ${entry.mastered ? 'opacity-70' : ''}`} style={{ ['--edge' as any]: entry.due && !entry.mastered ? '#ff4fd8' : '#3a2b7e' }}>
    <div className="flex flex-wrap items-start justify-between gap-2"><Meta entry={entry} /><EntryActions entry={entry} onChange={onChange} notify={notify} /></div>
    {d.instructions && <p className="mt-3 font-read text-xs italic text-fog">{d.instructions}</p>}
    <p className="mt-2 font-read text-[15px] leading-7"><b className="mr-2 font-terminal text-xl text-cyan">Q{d.n}</b>{entry.text}</p>
    {choice && d.type === 'matching' && d.options?.length > 0 && <div className="tile mt-2 grid gap-1 font-read text-xs sm:grid-cols-2">{d.options.map((o: any) => <span key={o.key}><b className="text-cyan">{o.key}</b> {o.text}</span>)}</div>}
    <div className="mt-3 flex flex-wrap items-center gap-2">
      {choice && d.options?.length > 0
        ? d.options.map((o: any) => <button key={o.key} onClick={() => retry(o.key)} className="btn-secondary !py-1 text-xs normal-case">{o.key}{d.type === 'mcq' ? ` · ${o.text}` : ''}</button>)
        : d.answer && <form className="flex gap-2" onSubmit={e => { e.preventDefault(); void retry() }}><input aria-label="Retry answer" className="input !w-52 !py-1.5" value={answer} onChange={e => setAnswer(e.target.value)} placeholder="Try again…" /><button className="btn-cyan !py-1"><RotateCcw size={14} /> Check</button></form>}
      {result !== null && <span className={`font-pixel ${result ? 'text-lime' : 'text-rose'}`}>{result ? '✓ Correct!' : '✗ Not yet'}</span>}
      <button className="btn-ghost" onClick={() => setReveal(!reveal)}><Eye size={14} /> {reveal ? 'Hide' : 'Show'} answer</button>
    </div>
    {reveal && <div className="tile mt-3 font-read text-sm"><p>Your answer: <span className="text-rose line-through">{d.given || '(blank)'}</span> → Correct: <b className="text-lime">{d.answer}</b></p>{d.evidence && <p className="mt-1 text-mist">Evidence: “{d.evidence}”</p>}</div>}
  </article>
}

/* ---------------- words ---------------- */
function WordCard({ entry, onChange, notify }: { entry: NotebookEntry; onChange: (e: NotebookEntry | null) => void; notify: Notify }) {
  const { persona } = usePersona()
  const d = entry.detail
  const [editing, setEditing] = useState(false)
  const [translation, setTranslation] = useState(d.translation || '')
  const save = async () => { try { onChange(await request<NotebookEntry>(`/notebook/${entry.id}`, { method: 'PATCH', body: JSON.stringify({ translation }) })); setEditing(false) } catch (e) { notify((e as Error).message, 'error') } }
  return <article className="panel p-5" style={{ ['--edge' as any]: entry.due && !entry.mastered ? '#3ef0ff' : '#3a2b7e' }}>
    <div className="flex items-start justify-between gap-2">
      <div><p className="flex items-center gap-2"><span className="font-pixel text-2xl text-cyan">{entry.text}</span><button onClick={() => speak(entry.text, persona, { force: true })} aria-label={`Pronounce ${entry.text}`} className="text-mist hover:text-cyan"><Volume2 size={17} /></button>{d.phonetic && <span className="font-read text-sm text-fog">{d.phonetic}</span>}</p><Meta entry={entry} /></div>
      <EntryActions entry={entry} onChange={onChange} notify={notify} />
    </div>
    {editing ? <form className="mt-3 flex gap-2" onSubmit={e => { e.preventDefault(); void save() }}><input aria-label="My meaning" className="input !py-1.5" value={translation} onChange={e => setTranslation(e.target.value)} placeholder="Meaning in your language" /><button className="btn-cyan !py-1">Save</button></form>
      : <p className="mt-3 font-read text-lime">{d.translation || <span className="text-fog">No translation yet</span>} <button className="btn-ghost !inline !px-1 text-xs" onClick={() => setEditing(true)}>edit</button></p>}
    {d.meanings?.length > 0 ? <ul className="mt-2 space-y-1 font-read text-sm">{d.meanings.slice(0, 3).map((m: any, i: number) => <li key={i}><i className="text-sun">{m.pos}</i> {m.definition}{m.example && <span className="block text-fog">“{m.example}”</span>}</li>)}</ul>
      : <p className="mt-2 font-read text-sm text-fog">No dictionary entry was available offline. <button className="btn-ghost !inline !px-1" onClick={() => askTutor(`I don't know the word "${entry.text}". What does it mean?`)}>Ask the tutor</button></p>}
    {d.synonyms?.length > 0 && <p className="mt-2 font-read text-xs text-mist">Synonyms: {d.synonyms.join(', ')}</p>}
    {d.collocations?.length > 0 && <p className="font-read text-xs text-mist">Collocations: {d.collocations.join(' · ')}</p>}
    {d.contexts?.filter(Boolean).length > 0 && <p className="mt-2 border-l-4 border-violet pl-3 font-read text-xs italic text-mist">{d.contexts.filter(Boolean)[0]}</p>}
  </article>
}

function WordReview({ words, onDone, notify }: { words: NotebookEntry[]; onDone: () => void; notify: Notify }) {
  const { persona } = usePersona()
  const [index, setIndex] = useState(0)
  const [show, setShow] = useState(false)
  const [score, setScore] = useState(0)
  const word = words[index]
  useEffect(() => { if (word) void speak(word.text, persona, { force: true }) }, [index])
  if (!word) return <div className="panel panel-lime p-8 text-center"><p className="font-pixel text-3xl text-lime">Review complete ✦</p><p className="mt-2 font-read text-mist">You remembered {score} of {words.length}. Forgotten words come back in 10 minutes; remembered ones are spaced out further.</p><button className="btn-primary mt-5" onClick={onDone}>Back to Word book</button></div>
  const answer = async (remembered: boolean) => {
    try { await post(`/notebook/${word.id}/review`, { remembered }); if (remembered) setScore(s => s + 1); setShow(false); setIndex(i => i + 1) } catch (e) { notify((e as Error).message, 'error') }
  }
  const d = word.detail
  return <div className="panel panel-cyan mx-auto max-w-xl p-8 text-center">
    <p className="font-pixel text-sm text-mist">{index + 1} / {words.length}</p>
    <p className="mt-6 font-pixel text-5xl text-cyan">{word.text}</p>
    {d.phonetic && <p className="mt-2 font-read text-fog">{d.phonetic}</p>}
    <button onClick={() => speak(word.text, persona, { force: true })} className="btn-ghost mt-2"><Volume2 size={15} /> hear it</button>
    {d.contexts?.[0] && <p className="mt-4 font-read text-sm italic text-mist">“{d.contexts[0]}”</p>}
    {show ? <div className="tile mt-6 text-left font-read"><p className="text-lime">{d.translation}</p>{d.meanings?.slice(0, 2).map((m: any, i: number) => <p key={i} className="mt-1 text-sm"><i className="text-sun">{m.pos}</i> {m.definition}</p>)}</div>
      : <button className="btn-secondary mt-6" onClick={() => setShow(true)}><Eye size={15} /> Show meaning</button>}
    <div className="mt-6 flex justify-center gap-3"><button className="btn-danger" onClick={() => answer(false)}><X size={16} /> Forgot</button><button className="btn-lime" onClick={() => answer(true)}><Check size={16} /> Remembered</button></div>
  </div>
}

/* ---------------- grammar & sentences ---------------- */
function GrammarCard({ entry, onChange, notify }: { entry: NotebookEntry; onChange: (e: NotebookEntry | null) => void; notify: Notify }) {
  const d = entry.detail
  return <article className="panel p-5">
    <div className="flex flex-wrap items-start justify-between gap-2"><Meta entry={entry} /><EntryActions entry={entry} onChange={onChange} notify={notify} /></div>
    <p className="mt-3 font-read text-[15px] text-rose/90 line-through decoration-rose/50">{entry.text}</p>
    {d.correction && <p className="mt-1 font-read text-[15px] text-lime">→ {d.correction}</p>}
    <p className="mt-2 font-read text-sm text-mist">{d.suggestion}</p>
    <button className="btn-ghost mt-2 !px-0 text-xs" onClick={() => askTutor(`Please explain this grammar point with two more examples: "${d.issue}". My sentence was: "${entry.text}"`)}>Ask the tutor to explain →</button>
  </article>
}

function SentenceCard({ entry, onChange, notify }: { entry: NotebookEntry; onChange: (e: NotebookEntry | null) => void; notify: Notify }) {
  const { persona } = usePersona()
  const d = entry.detail
  return <article className="panel p-5" style={{ ['--edge' as any]: '#b8ff5c88' }}>
    <div className="flex flex-wrap items-start justify-between gap-2"><Meta entry={entry} /><EntryActions entry={entry} onChange={onChange} notify={notify} /></div>
    <p className="mt-3 font-read text-[16px] leading-7 text-moon">“{entry.text}” <button onClick={() => speak(entry.text, persona, { force: true })} aria-label="Read sentence aloud" className="align-middle text-mist hover:text-cyan"><Volume2 size={15} /></button></p>
    {d.original && <p className="mt-1 font-read text-xs text-fog">Your original: {d.original}</p>}
    {d.patterns?.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{d.patterns.map((p: string) => <span key={p} className="pill text-lime">{p}</span>)}</div>}
    {d.note && <p className="mt-2 font-read text-sm text-mist">{d.note}</p>}
  </article>
}

function AddForm({ kind, onAdded, notify }: { kind: 'grammar' | 'sentence' | 'word'; onAdded: () => void; notify: Notify }) {
  const [text, setText] = useState('')
  const [extra, setExtra] = useState('')
  const [open, setOpen] = useState(false)
  const submit = async () => {
    try {
      await post('/notebook', kind === 'grammar' ? { kind, text, correction: extra || null, source: 'Added manually' } : kind === 'sentence' ? { kind, text, note: extra || null, source: 'Added manually' } : { kind, text, context: extra, source: 'Added manually', language: localStorage.getItem('native-language') || 'Chinese (Simplified)' })
      setText(''); setExtra(''); setOpen(false); onAdded(); notify('Saved')
    } catch (e) { notify((e as Error).message, 'error') }
  }
  if (!open) return <button className="btn-secondary" onClick={() => setOpen(true)}><Plus size={15} /> Add {kind === 'word' ? 'a word' : kind === 'grammar' ? 'a grammar note' : 'a sentence'}</button>
  return <form className="panel panel-flat grid gap-2 p-4 md:grid-cols-[1fr_1fr_auto]" onSubmit={e => { e.preventDefault(); void submit() }}>
    <input aria-label="Entry text" className="input" value={text} onChange={e => setText(e.target.value)} placeholder={kind === 'word' ? 'Word or phrase' : kind === 'grammar' ? 'The incorrect sentence' : 'An advanced sentence to remember'} />
    <input aria-label="Extra detail" className="input" value={extra} onChange={e => setExtra(e.target.value)} placeholder={kind === 'word' ? 'Sentence where you saw it (optional)' : kind === 'grammar' ? 'Correct version (optional)' : 'Why it is useful (optional)'} />
    <button className="btn-cyan" disabled={!text.trim()}>Save</button>
  </form>
}

export default function NotebookPage({ notify }: { notify: Notify }) {
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) || 'overview'
  const go = (next: Tab) => setParams(next === 'overview' ? {} : { tab: next })
  const [stats, setStats] = useState<NotebookStats | null>(null)
  const [filter, setFilter] = useState('all')
  const [showMastered, setShowMastered] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const { entries, setEntries, reload } = useEntries(tab === 'overview' ? null : tab)
  const loadStats = () => request<NotebookStats>('/notebook/stats').then(setStats).catch(() => {})
  useEffect(() => { loadStats(); setFilter('all'); setReviewing(false) }, [tab])
  useEffect(() => { const on = () => loadStats(); window.addEventListener('notebook-changed', on); return () => window.removeEventListener('notebook-changed', on) }, [])
  const update = (id: number) => (next: NotebookEntry | null) => { setEntries(prev => (prev || []).flatMap(e => e.id === id ? (next ? [next] : []) : [e])); loadStats() }
  const categories = useMemo(() => Array.from(new Set((entries || []).map(e => tab === 'mistake' ? e.category : e.skill).filter(Boolean))), [entries, tab])
  const visible = (entries || []).filter(e => (showMastered || !e.mastered) && (filter === 'all' || (tab === 'mistake' ? e.category : e.skill) === filter))
    .sort((a, b) => Number(b.due) - Number(a.due) || b.count - a.count)
  const dueWords = (entries || []).filter(e => e.kind === 'word' && e.due && !e.mastered)

  return <>
    <PageTitle eyebrow="Your learning grimoire" title="Notebooks" subtitle="Every wrong answer, unknown word, grammar slip and great sentence — recorded automatically from your practice, from the AI tutor, or by selecting text anywhere."
      action={<Link to="/tutor" className="btn-primary"><BookMarked size={16} /> Ask the AI tutor</Link>} />
    <nav className="mb-6 flex flex-wrap gap-1" aria-label="Notebooks">{TABS.map(([key, label]) => <button key={key} onClick={() => go(key)} className={tab === key ? 'btn-primary' : 'btn-secondary'}>
      {label}{key !== 'overview' && stats ? <span className="font-read text-xs opacity-80">{stats.counts[key as NotebookKind]?.active ?? 0}</span> : null}
    </button>)}</nav>
    {tab === 'overview' ? (stats ? <Overview stats={stats} go={go} /> : <Spinner />)
      : !entries ? <Spinner />
        : reviewing ? <WordReview words={dueWords} notify={notify} onDone={() => { setReviewing(false); reload(); loadStats() }} />
          : <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              {categories.length > 1 && <select aria-label="Filter" className="input !w-auto !py-1.5" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All {tab === 'mistake' ? 'question types' : 'skills'}</option>{categories.map(c => <option key={c} value={c}>{nice(c)}</option>)}</select>}
              <label className="flex items-center gap-2 font-pixel text-sm text-mist"><input type="checkbox" checked={showMastered} onChange={e => setShowMastered(e.target.checked)} className="accent-magenta" /> Show mastered</label>
              {tab === 'word' && <button className="btn-cyan" disabled={!dueWords.length} onClick={() => setReviewing(true)}>Review {dueWords.length} due word{dueWords.length === 1 ? '' : 's'}</button>}
              {tab !== 'mistake' && <AddForm kind={tab} onAdded={() => { reload(); loadStats() }} notify={notify} />}
            </div>
            {!visible.length ? <Empty title="Nothing here yet" body={{ mistake: 'Wrong answers from listening, reading and mock exams are saved here automatically.', word: 'Select a word on any page and press “Word book”, or tell the tutor “I don’t know the word …”.', grammar: 'Grammar errors from your writing and speaking feedback are saved here, grouped by type.', sentence: 'Corrected rewrites from your feedback are saved here. Select any great sentence and press “Sentence book”.' }[tab]} />
              : <div className={`grid gap-4 ${tab === 'word' ? 'md:grid-cols-2 xl:grid-cols-3' : 'lg:grid-cols-2'}`}>{visible.map(entry =>
                tab === 'mistake' ? <MistakeCard key={entry.id} entry={entry} onChange={update(entry.id)} notify={notify} />
                  : tab === 'word' ? <WordCard key={entry.id} entry={entry} onChange={update(entry.id)} notify={notify} />
                    : tab === 'grammar' ? <GrammarCard key={entry.id} entry={entry} onChange={update(entry.id)} notify={notify} />
                      : <SentenceCard key={entry.id} entry={entry} onChange={update(entry.id)} notify={notify} />)}</div>}
          </div>}
  </>
}

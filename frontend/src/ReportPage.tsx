import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, BookOpen, CheckCircle2, FileText, Headphones, Mic, TrendingDown, TrendingUp, TriangleAlert } from 'lucide-react'
import { Result } from './api'
import { HeldNotice, PageTitle, Spinner, nice, stamp, useLoad } from './ui'

type Section = Record<string, any>
const ICONS = { listening: Headphones, reading: BookOpen, writing: FileText, speaking: Mic } as const
const KIND_STYLE: Record<string, string> = { 'not written': 'text-sun', misspelled: 'text-cyan', wrong: 'text-rose' }

function List({ title, items, tone }: { title: string; items: string[]; tone: 'good' | 'bad' }) {
  const Icon = tone === 'good' ? CheckCircle2 : TriangleAlert
  return <div>
    <h4 className={`flex items-center gap-2 font-pixel ${tone === 'good' ? 'text-lime' : 'text-sun'}`}><Icon size={16} /> {title}</h4>
    {items.length ? <ul className="mt-2 space-y-1 font-read text-sm">{items.map((item, i) => <li key={i}>▸ {item}</li>)}</ul>
      : <p className="mt-2 font-read text-sm text-mist">{tone === 'good' ? 'Nothing stood out yet in this section.' : 'No clear problems found.'}</p>}
  </div>
}

/* Listening and reading: question types, and every missed question with the correct answer. */
function Objective({ s }: { s: Section }) {
  return <>
    {s.question_types?.length > 0 && <div>
      <h4 className="font-pixel text-cyan">By question type</h4>
      <div className="mt-2 space-y-2">{s.question_types.map((t: Section) => <div key={t.type} className="font-read text-sm">
        <div className="flex justify-between"><span>{t.type}</span><span className={t.accuracy >= .7 ? 'text-lime' : t.accuracy < .5 ? 'text-rose' : 'text-sun'}>{t.correct}/{t.total}</span></div>
        <div className="mt-1 h-2 bg-abyss"><div className={`h-2 ${t.accuracy >= .7 ? 'bg-lime' : t.accuracy < .5 ? 'bg-rose' : 'bg-sun'}`} style={{ width: `${Math.round(t.accuracy * 100)}%` }} /></div>
      </div>)}</div>
    </div>}
    {(s.words_not_written?.length > 0 || s.misspelled?.length > 0) && <div className="grid gap-4 sm:grid-cols-2">
      {s.words_not_written?.length > 0 && <div><h4 className="font-pixel text-sun">Words you didn't write</h4>
        <div className="mt-2 flex flex-wrap gap-2">{s.words_not_written.map((w: string, i: number) => <span key={i} className="pill text-sun">{w}</span>)}</div></div>}
      {s.misspelled?.length > 0 && <div><h4 className="font-pixel text-cyan">Misspelled</h4>
        <ul className="mt-2 space-y-1 font-read text-sm">{s.misspelled.map((m: Section, i: number) => <li key={i}><span className="text-rose line-through">{m.you_wrote}</span> → <span className="text-lime">{m.correct}</span></li>)}</ul></div>}
    </div>}
    {s.missed?.length > 0 && <details className="tile">
      <summary className="cursor-pointer font-pixel">Every missed question ({s.missed.length})</summary>
      <div className="mt-3 overflow-x-auto"><table className="w-full font-read text-sm">
        <thead><tr className="text-left text-mist"><th className="pr-3">Q</th><th className="pr-3">Question</th><th className="pr-3">Your answer</th><th className="pr-3">Correct</th><th>Problem</th></tr></thead>
        <tbody>{s.missed.map((m: Section) => <tr key={m.n} className="border-t border-violet/40 align-top">
          <td className="py-1 pr-3">{m.n}</td><td className="py-1 pr-3">{m.question || m.type}</td><td className="py-1 pr-3">{m.your_answer || '—'}</td>
          <td className="py-1 pr-3 text-lime">{m.correct_answer}</td><td className={`py-1 ${KIND_STYLE[m.kind] || ''}`}>{m.kind}</td></tr>)}</tbody>
      </table></div>
    </details>}
  </>
}

/* Writing and speaking: grammar by type with corrections, vocabulary, task and fluency. */
function Production({ s }: { s: Section }) {
  const v = s.vocabulary || {}
  return <>
    {s.criteria?.length > 0 && <div className="flex flex-wrap gap-2">{s.criteria.map((c: Section) => <span key={c.name} className={`pill ${c.status === 'strength' ? 'text-lime' : 'text-sun'}`}>{nice(c.name)} {c.score}</span>)}</div>}
    {s.fluency && <div className="flex flex-wrap gap-2 font-read text-sm">
      {s.fluency.words_per_minute != null && <span className="pill text-cyan">{s.fluency.words_per_minute} words/min</span>}
      {s.fluency.fillers != null && <span className="pill text-cyan">{s.fluency.fillers} fillers</span>}
      {s.fluency.average_turn_words != null && <span className="pill text-cyan">{s.fluency.average_turn_words} words per answer</span>}
      {s.fluency.part2_words != null && <span className="pill text-cyan">Part 2: {s.fluency.part2_words} words</span>}
    </div>}
    <div>
      <h4 className="font-pixel text-rose">Grammar mistakes by type</h4>
      {s.grammar?.length ? <div className="mt-2 space-y-3">{s.grammar.map((g: Section) => <div key={g.type} className="tile font-read text-sm">
        <p><b className="font-pixel">{g.type}</b> <span className="text-mist">× {g.count}</span></p>
        <p className="text-mist">{g.advice}</p>
        {g.examples?.map((e: Section, i: number) => <p key={i} className="mt-1"><span className="text-fog">“{e.sentence}”</span>{e.correction && <> → <span className="text-lime">{e.correction}</span></>}</p>)}
      </div>)}</div> : <p className="mt-2 font-read text-sm text-mist">No grammar mistakes were found.</p>}
    </div>
    <div>
      <h4 className="font-pixel text-cyan">Vocabulary</h4>
      <p className="mt-2 font-read text-sm">{v.words ?? 0} words{v.lexical_diversity != null ? ` · diversity ${v.lexical_diversity}` : ''}{v.linker_variety != null ? ` · ${v.linker_variety} different linking words` : ''}</p>
      {v.academic_words?.length > 0 && <p className="font-read text-sm text-lime">Academic words used: {v.academic_words.join(', ')}</p>}
      {v.repeated_words?.length > 0 && <p className="font-read text-sm text-sun">Repeated often: {v.repeated_words.join(', ')} (try synonyms)</p>}
      {v.issues?.map((i: Section) => <p key={i.type} className="font-read text-sm text-mist">▸ {i.type}: {i.advice}</p>)}
    </div>
    {s.task_issues?.length > 0 && <div><h4 className="font-pixel text-sun">Task and organisation</h4>
      {s.task_issues.map((t: Section) => <p key={t.type} className="mt-1 font-read text-sm">▸ <b>{t.type}</b>: <span className="text-mist">{t.advice}</span></p>)}</div>}
    {s.better_sentences?.length > 0 && <div><h4 className="font-pixel text-lime">Better versions of your sentences</h4>
      {s.better_sentences.map((b: Section, i: number) => <div key={i} className="mt-2 font-read text-sm"><p className="text-fog line-through decoration-rose/70">{b.original}</p><p className="text-lime">{b.improved}</p></div>)}</div>}
    {s.pronunciation_note && <p className="font-read text-xs text-sun">{s.pronunciation_note}</p>}
  </>
}

function SectionCard({ skill, s }: { skill: keyof typeof ICONS; s: Section }) {
  const Icon = ICONS[skill]
  const tasks: Section[] = s.tasks || []
  return <section className="panel space-y-5 p-6 anim-page" aria-label={`${skill} report`}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="section-title flex items-center gap-2"><Icon className="text-magenta" /> {nice(skill)}</h3>
      <div className="flex items-center gap-3 font-read text-sm text-mist">{s.source && <span>{s.source}</span>}
        {s.raw != null && <span>{s.raw}/{s.total} correct</span>}{s.score != null && <span className="num text-4xl text-magenta">{s.score}</span>}</div>
    </div>
    <div className="grid gap-5 md:grid-cols-2"><List title="What went well" items={s.went_well || []} tone="good" /><List title="What to improve" items={s.to_improve || []} tone="bad" /></div>
    {skill === 'listening' || skill === 'reading' ? <Objective s={s} />
      : skill === 'writing' ? tasks.map(t => <div key={t.task} className="space-y-4 border-t border-violet/40 pt-4">
          <h4 className="font-pixel text-lg text-sun">{t.task === 'task1' ? 'Task 1' : t.task === 'task2' ? 'Task 2' : nice(t.task)}{t.band != null ? ` · band ${t.band}` : ''}</h4><Production s={t} /></div>)
        : <Production s={s} />}
  </section>
}

export default function ReportPage() {
  const { id } = useParams()
  const { data, loading, error, reload } = useLoad<{ id: number; created_at: string; result: Result }>(`/reports/${id}`, [id])
  // UC6 8a: the report cannot be displayed; the assessment data is kept for a later attempt.
  if (error && !data) return <div className="panel panel-sun mx-auto mt-10 max-w-xl space-y-4 p-7 text-center" role="alert">
    <h2 className="section-title">Report currently unavailable</h2><p className="font-read text-mist">{error}</p>
    <p className="font-read text-sm text-mist">Your results are kept, so you can try again later.</p>
    <div className="flex flex-wrap justify-center gap-2"><button className="btn-primary" disabled={loading} onClick={reload}>{loading ? 'Trying…' : 'Try again'}</button>
      <Link to="/analytics" className="btn-secondary">Back to performance</Link></div></div>
  if (loading || !data) return <Spinner label="Opening your report…" />
  const result = data.result
  if (result.state !== 'RELEASED' || !result.payload) return <><PageTitle eyebrow="Performance report" title={`Report #${data.id}`} /><HeldNotice result={result} /></>
  const p = result.payload
  const sections: Record<string, Section> = p.sections || {}
  const mock = p.mock_summary
  const readiness = mock?.readiness_detail
  return <>
    <PageTitle eyebrow={p.trigger?.kind === 'mock_exam' ? `Generated after mock #${p.trigger.mock_id}` : `Performance report · ${stamp(data.created_at)}`} title={`Report #${data.id}`}
      subtitle="Section by section: what went well, what to improve, the question types and words you missed, and your grammar by type."
      action={<Link to="/analytics" className="btn-secondary"><ArrowLeft size={16} /> Performance</Link>} />
    <div className="panel panel-hot mb-6 grid gap-6 p-6 md:grid-cols-[auto_1fr]">
      {mock?.estimated_overall != null && <div className="grid h-28 w-28 place-items-center bg-abyss" style={{ boxShadow: '0 0 0 4px #ff4fd8' }}><span className="num text-7xl text-magenta">{mock.estimated_overall}</span></div>}
      <div className="space-y-2 font-read">
        <p className="font-pixel text-xl text-cyan">{readiness?.level || p.readiness}{readiness?.gap > 0 ? ` · ${readiness.gap} to target` : ''}</p>
        <p className="leading-7">{readiness?.explanation || p.readiness_note}</p>
        <p className="text-sm text-mist">{p.summary}</p>
        {mock?.comparison?.skills && <p className="text-sm">{Object.entries(mock.comparison.skills).map(([k, c]: [string, any]) => <span key={k} className="mr-3 inline-flex items-center gap-1">
          {c.change > 0 ? <TrendingUp size={14} className="text-lime" /> : c.change < 0 ? <TrendingDown size={14} className="text-rose" /> : null}{nice(k)} {c.before} → {c.now}</span>)}</p>}
      </div>
    </div>
    <div className="space-y-6">
      {(['listening', 'reading', 'writing', 'speaking'] as const).map(skill => sections[skill]
        ? <SectionCard key={skill} skill={skill} s={sections[skill]} />
        : <div key={skill} className="panel p-5 font-read text-mist">{nice(skill)}: no verified result yet. <Link to={`/practice/${skill}`} className="text-cyan underline">Practise {skill}</Link></div>)}
    </div>
    <div className="mt-6 grid gap-6 lg:grid-cols-2">
      <div className="panel p-6"><h3 className="section-title">Patterns across all your practice</h3>
        {p.patterns?.mistakes_by_type?.length > 0 && <><p className="mt-3 font-pixel text-sun">Most-missed question types</p>{p.patterns.mistakes_by_type.map((m: Section) => <p key={m.name} className="font-read text-sm">▸ {m.name} × {m.count}</p>)}</>}
        {p.patterns?.grammar_issues?.length > 0 && <><p className="mt-3 font-pixel text-rose">Repeated grammar problems</p>{p.patterns.grammar_issues.map((g: Section) => <p key={g.name} className="font-read text-sm">▸ {g.name} × {g.count}</p>)}</>}
        {!p.patterns?.mistakes_by_type?.length && !p.patterns?.grammar_issues?.length && <p className="mt-3 font-read text-sm text-mist">Patterns appear after a few practice sessions.</p>}
        <Link to="/notebook" className="btn-ghost mt-3 !px-0 text-sm">Open your notebooks →</Link></div>
      <div className="panel p-6"><h3 className="section-title">What to do next</h3>
        {p.recommendations?.length ? <ul className="mt-3 space-y-2 font-read text-sm">{p.recommendations.map((r: string) => <li key={r} className="tile">{r}</li>)}</ul>
          : <p className="mt-3 font-read text-sm text-sun">{p.recommendations_unavailable ? 'Recommendations were temporarily unavailable for this report. Generate a new report later to get them.' : 'No recommendations yet.'}</p>}
        {p.trend_note && <p className="mt-3 font-read text-xs text-mist">{p.trend_note}</p>}
        <Link to="/materials?recommend=1" className="btn-cyan mt-4 inline-flex">Recommended for me</Link></div>
    </div>
  </>
}

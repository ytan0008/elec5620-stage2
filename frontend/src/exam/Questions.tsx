import { Fragment } from 'react'
import { Check, Play, X } from 'lucide-react'
import { Group, Question, Section } from '../api'

export type Answers = Record<string, string>
export type ReviewItem = { n: number; given: string; answer: string; correct: boolean; evidence: string }

function Mark({ item }: { item?: ReviewItem }) {
  if (!item) return null
  return item.correct
    ? <span className="ml-2 inline-flex items-center gap-1 font-pixel text-sm text-lime"><Check size={15} /> correct</span>
    : <span className="ml-2 inline-flex flex-wrap items-center gap-1 font-pixel text-sm text-rose"><X size={15} /> answer: <b className="text-lime">{item.answer}</b></span>
}

function Num({ n }: { n: number }) {
  return <span className="mr-2 inline-grid h-7 min-w-7 place-items-center bg-violet px-1 font-terminal text-xl text-moon" style={{ boxShadow: '0 0 0 2px #140c2e' }}>{n}</span>
}

function Gap({ q, answers, setAnswer, disabled, review, width = 'w-40' }: { q: Question; answers: Answers; setAnswer: (n: number, v: string) => void; disabled: boolean; review?: ReviewItem; width?: string }) {
  return <input aria-label={`Answer ${q.n}`} disabled={disabled} value={answers[String(q.n)] || ''} onChange={e => setAnswer(q.n, e.target.value)}
    className={`mx-1 inline-block ${width} border-b-[3px] bg-abyss/70 px-2 py-0.5 font-read text-[15px] text-cyan outline-none focus:border-magenta ${review ? (review.correct ? 'border-lime' : 'border-rose') : 'border-violet'}`} />
}

export function GroupView({ group, answers, setAnswer, disabled = false, review, onPlayClip }: { group: Group; answers: Answers; setAnswer: (n: number, value: string) => void; disabled?: boolean; review?: Record<number, ReviewItem>; onPlayClip?: (q: Question) => void }) {
  const choiceButtons = (q: Question, options: { key: string; text: string }[], compact = false) =>
    <div className={`mt-2 flex ${compact ? 'flex-wrap gap-2' : 'flex-col gap-1.5'}`} role="radiogroup" aria-label={`Question ${q.n}`}>
      {options.map(option => {
        const chosen = answers[String(q.n)] === option.key
        return <button type="button" role="radio" aria-checked={chosen} key={option.key} disabled={disabled} onClick={() => setAnswer(q.n, chosen ? '' : option.key)}
          className={`flex items-start gap-2 px-3 py-1.5 text-left font-read text-[15px] transition-colors ${chosen ? 'bg-magenta text-night' : 'bg-abyss/60 text-moon hover:bg-plum'}`}
          style={{ boxShadow: `0 0 0 2px ${chosen ? '#ff4fd8' : '#3a2b7e'}` }}>
          <b className="font-pixel">{option.key}</b>{!compact && <span>{option.text}</span>}
        </button>
      })}
    </div>
  return <section className="space-y-4" aria-label={group.title}>
    <div>
      <h3 className="font-pixel text-lg text-sun">{group.title}</h3>
      <p className="mt-1 font-read text-sm italic text-mist">{group.instructions}</p>
      {group.heading && <p className="mt-3 inline-block bg-plum px-3 py-1 font-pixel text-moon" style={{ boxShadow: '0 0 0 2px #6b52d6' }}>{group.heading}</p>}
    </div>
    {group.type === 'matching' && group.options && <div className="tile grid gap-1 font-read text-sm sm:grid-cols-2">{group.options.map(option => <div key={option.key}><b className="mr-2 font-pixel text-cyan">{option.key}</b>{option.text}</div>)}</div>}
    {group.type === 'cwords' && group.text && <p className="tile font-read text-[15.5px] leading-9">
      {group.text.split(/(\{\{\d+\}\})/).map((part, i) => {
        const match = part.match(/\{\{(\d+)\}\}/)
        if (!match) return <Fragment key={i}>{part}</Fragment>
        const q = group.questions.find(item => item.n === Number(match[1]))!
        return <span key={i} className="whitespace-nowrap"><sup className="font-terminal text-fog">{q.n}</sup><Gap q={q} answers={answers} setAnswer={setAnswer} disabled={disabled} review={review?.[q.n]} width="w-32" /><Mark item={review?.[q.n]} /></span>
      })}
    </p>}
    {group.type !== 'cwords' && <ol className="space-y-4">
      {group.questions.map(q => <li key={q.n} className="font-read text-[15px] leading-7">
        {q.clip && onPlayClip && <button type="button" onClick={() => onPlayClip(q)} className="btn-cyan mb-1 !px-2 !py-1 text-xs"><Play size={14} /> Play recording {q.n}</button>}
        {group.type === 'completion' ? <div className="flex flex-wrap items-center">
          <Num n={q.n} />
          {(q.prompt || '___').split('___').map((part, i, all) => <Fragment key={i}>{part}{i < all.length - 1 && <Gap q={q} answers={answers} setAnswer={setAnswer} disabled={disabled} review={review?.[q.n]} />}</Fragment>)}
          <Mark item={review?.[q.n]} />
        </div> : <div>
          <div className="flex items-start"><Num n={q.n} /><span className="pt-0.5">{q.prompt}</span><Mark item={review?.[q.n]} /></div>
          {group.type === 'mcq' && choiceButtons(q, q.options || [])}
          {(group.type === 'tfng' || group.type === 'ynng') && choiceButtons(q, group.options || [], true)}
          {group.type === 'matching' && <select aria-label={`Answer ${q.n}`} disabled={disabled} className="input mt-2 max-w-xs" value={answers[String(q.n)] || ''} onChange={e => setAnswer(q.n, e.target.value)}>
            <option value="">— choose —</option>{(group.options || []).map(option => <option key={option.key} value={option.key}>{option.key}  {option.text.slice(0, 48)}</option>)}
          </select>}
        </div>}
        {review?.[q.n] && !review[q.n].correct && review[q.n].evidence && <p className="ml-9 mt-1 text-sm text-fog">Evidence: “{review[q.n].evidence}”</p>}
      </li>)}
    </ol>}
  </section>
}

export function SectionQuestions({ section, ...rest }: { section: Section; answers: Answers; setAnswer: (n: number, value: string) => void; disabled?: boolean; review?: Record<number, ReviewItem>; onPlayClip?: (q: Question) => void }) {
  return <div className="space-y-8">{section.groups.map(group => <GroupView key={group.title} group={group} {...rest} />)}</div>
}

export const questionCount = (sections: Section[]) => sections.reduce((sum, section) => sum + section.groups.reduce((s, g) => s + g.questions.length, 0), 0)
export const answeredCount = (sections: Section[], answers: Answers) => sections.reduce((sum, section) => sum + section.groups.reduce((s, g) => s + g.questions.filter(q => (answers[String(q.n)] || '').trim()).length, 0), 0)

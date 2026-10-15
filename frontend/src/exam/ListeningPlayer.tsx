import { useEffect, useRef, useState } from 'react'
import { Pause, Play, SkipBack, SkipForward, Volume2 } from 'lucide-react'
import { Question, ScriptLine, Section } from '../api'
import { prefetch, speak, stopSpeaking, VoiceRole } from '../voice'

type Props = { sections: Section[]; mode: 'exam' | 'practice'; onFinished?: () => void }
const READING_PAUSE = /you have some time|before you hear|first, you have/i

/* Plays multi-speaker scripts with distinct voices. Exam mode plays once without pausing, like the real test. */
export default function ListeningPlayer({ sections, mode, onFinished }: Props) {
  const lines = sections.flatMap(section => (section.script || []).map(line => ({ ...line, section: section.title })))
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [started, setStarted] = useState(false)
  const [finished, setFinished] = useState(false)
  const [rate, setRate] = useState(1)
  const [reading, setReading] = useState(0)
  const run = useRef(0)
  useEffect(() => () => { run.current++; stopSpeaking() }, [])

  const playFrom = async (start: number) => {
    const token = ++run.current
    setPlaying(true)
    setStarted(true)
    for (let i = start; i < lines.length; i++) {
      if (run.current !== token) return
      setIndex(i)
      if (lines[i + 1]) prefetch(lines[i + 1].text, lines[i + 1].voice as VoiceRole, rate)
      await speak(lines[i].text, lines[i].voice as VoiceRole, { rate, force: true })
      if (run.current !== token) return
      if (lines[i].voice === 'narrator' && READING_PAUSE.test(lines[i].text)) {
        const wait = mode === 'exam' ? 20 : 8
        for (let s = wait; s > 0; s--) {
          if (run.current !== token) return
          setReading(s)
          await new Promise(resolve => window.setTimeout(resolve, 1000))
        }
        setReading(0)
      } else {
        await new Promise(resolve => window.setTimeout(resolve, 380))
      }
    }
    if (run.current === token) { setPlaying(false); setFinished(true); setIndex(lines.length); onFinished?.() }
  }
  const pause = () => { run.current++; stopSpeaking(); setPlaying(false); setReading(0) }
  const jump = (to: number) => { pause(); const next = Math.max(0, Math.min(lines.length - 1, to)); setIndex(next); void playFrom(next) }

  if (!lines.length) return <p className="tile font-read text-sm text-mist"><Volume2 size={15} className="mr-1 inline" />Each question has its own short recording. Press its play button.</p>
  const current = lines[Math.min(index, lines.length - 1)]
  const progress = Math.round((finished ? 1 : index / lines.length) * 100)
  return <div className="panel panel-cyan p-5" role="region" aria-label="Audio player">
    <div className="flex flex-wrap items-center gap-4">
      <div className="flex h-12 items-end gap-1" aria-hidden>{Array.from({ length: 9 }, (_, i) => <span key={i} className={`block w-2 ${playing && !reading ? 'eq-bar' : ''}`} style={{ height: playing && !reading ? undefined : 6, background: i % 2 ? '#ff4fd8' : '#3ef0ff', animationDelay: `${i * .09}s` }} />)}</div>
      <div className="min-w-0 flex-1">
        <p className="font-pixel text-sm uppercase tracking-wider text-mist">{finished ? 'Recording finished' : !started ? 'Ready to play' : reading ? `Reading time · ${reading}s` : `Now speaking · ${current.speaker}`}</p>
        <div className="bar mt-2"><span style={{ width: `${progress}%` }} /></div>
      </div>
      {mode === 'exam'
        ? !started && <button className="btn-cyan" onClick={() => playFrom(0)}><Play size={17} /> Start audio</button>
        : <div className="flex flex-wrap items-center gap-1">
          <button className="btn-secondary !px-2" aria-label="Previous line" onClick={() => jump(index - 1)}><SkipBack size={16} /></button>
          {playing ? <button className="btn-cyan" onClick={pause}><Pause size={17} /> Pause</button> : <button className="btn-cyan" onClick={() => playFrom(finished ? 0 : index)}><Play size={17} /> {finished ? 'Replay' : started ? 'Resume' : 'Play'}</button>}
          <button className="btn-secondary !px-2" aria-label="Next line" onClick={() => jump(index + 1)}><SkipForward size={16} /></button>
          <select aria-label="Playback speed" className="input !w-24 !py-1.5" value={rate} onChange={e => { setRate(Number(e.target.value)); if (playing) pause() }}>
            {[.8, .9, 1, 1.15, 1.3].map(value => <option key={value} value={value}>{value}×</option>)}
          </select>
        </div>}
    </div>
    {mode === 'exam' && started && !finished && <p className="mt-3 font-read text-xs text-fog">As in the real test, the recording plays once. Answer while you listen.</p>}
  </div>
}

/* TOEFL "Listen and Choose a Response": each item has its own clip. */
export function useClipPlayer(mode: 'exam' | 'practice') {
  const [played, setPlayed] = useState<number[]>([])
  const play = async (question: Question) => {
    if (!question.clip) return
    if (mode === 'exam' && played.includes(question.n)) return
    setPlayed(previous => [...previous, question.n])
    for (const line of question.clip as ScriptLine[]) await speak(line.text, line.voice as VoiceRole, { force: true })
  }
  return { play, played }
}

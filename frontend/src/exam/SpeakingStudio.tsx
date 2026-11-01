import { useEffect, useRef, useState } from 'react'
import { Keyboard, Mic, MicOff, Play, RotateCcw, Square, Volume2 } from 'lucide-react'
import { Result, SpeakingView, health, post, request, retryOnce } from '../api'
import { PixelAvatar, personaName } from '../pixel/Avatar'
import { moodFor, usePersona } from '../persona'
import { Listener, listen, monitorLevel, prefs, recognitionSupported, recordMicrophone, speak, stopSpeaking, transcribeOnServer } from '../voice'
import { Countdown, FeedbackPanel, Notify, clock } from '../ui'
import { useExamLock } from '../examLock'

type Props = { notify: Notify; mockId?: number; questionId?: string | null; onSaved?: () => void; onResult?: (result: Result) => void }
const SILENCE: Record<string, number> = { p2_talk: 7000, repeat: 2500, interview: 4500 }
const DEFAULT_SILENCE = 4000 // Part 1 and Part 3
const MIN_ANSWER_MS = 1500 // never send before this much of the answer has been heard
const CAP: Record<string, number> = { p2_talk: 120, repeat: 15, interview: 45 }

export default function SpeakingStudio({ notify, mockId, questionId, onSaved, onResult }: Props) {
  const { persona, aiSpeaking } = usePersona()
  const [session, setSession] = useState<SpeakingView | null>(null)
  const [listening, setListening] = useState(false)
  const [thinking, setThinking] = useState(false)
  const [caption, setCaption] = useState('')
  const [typed, setTyped] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [prep, setPrep] = useState(false)
  const [result, setResult] = useState<Result | null>(null)
  const [metrics, setMetrics] = useState<Record<string, number> | null>(null)
  const [handsFree, setHandsFree] = useState(prefs.handsFree)
  const [serverStt, setServerStt] = useState(false)
  // 'server' records the answer and recognises it on our server (offline Whisper or cloud); 'browser' uses the browser's online service.
  const [mode, setMode] = useState<'server' | 'browser' | 'none'>(recognitionSupported() ? 'browser' : 'none')
  const [level, setLevel] = useState(0)
  const [error, setError] = useState('')
  const [starting, setStarting] = useState(false)
  const modeRef = useRef(mode)
  const stopLevel = useRef<(() => void) | null>(null)
  const finishing = useRef(false)
  const sessionRef = useRef<SpeakingView | null>(null)
  const listener = useRef<Listener | null>(null)
  const textRef = useRef({ final: '', interim: '' })
  const started = useRef(0)
  const silenceTimer = useRef(0)
  const tickTimer = useRef(0)
  const recorder = useRef<{ stop: () => Promise<Blob> } | null>(null)
  const sttRecorder = useRef<{ stop: () => Promise<Blob>; stream: MediaStream } | null>(null)
  const alive = useRef(true)
  useExamLock(`speaking-${mockId ?? 'practice'}`, session?.status === 'ACTIVE')

  const chooseMode = (next: 'server' | 'browser' | 'none') => { modeRef.current = next; setMode(next) }
  useEffect(() => { health().then(h => { setServerStt(h.server_stt); if (h.server_stt) chooseMode('server') }).catch(() => {}) }, [])
  useEffect(() => () => { alive.current = false; listener.current?.abort(); stopSpeaking(); stopLevel.current?.(); window.clearTimeout(silenceTimer.current); window.clearInterval(tickTimer.current); void recorder.current?.stop(); void sttRecorder.current?.stop() }, [])

  const stage = session?.ui.stage || 'intro'
  const lastExaminer = [...(session?.log || [])].reverse().find(item => item.role === 'examiner')
  const apply = (view: SpeakingView) => { sessionRef.current = view; setSession(view) }

  const say = async (text: string, view: SpeakingView) => {
    await speak(text, persona, { force: true })
    if (!alive.current) return
    afterSpeech(view)
  }
  const afterSpeech = (view: SpeakingView) => {
    if (view.ui.stage === 'p2_prep') { setPrep(true); return }
    if (view.ui.stage === 'done' || view.status !== 'ACTIVE') { void finish(); return }
    if (prefs.handsFree && modeRef.current !== 'none') startListening()
  }

  const begin = async () => {
    setError(''); setResult(null); setStarting(true)
    try { recorder.current = await recordMicrophone() } catch { recorder.current = null }
    try {
      const view = await retryOnce(() => post<SpeakingView>('/speaking/sessions', { persona, ...(mockId ? { mock_id: mockId } : {}), ...(questionId ? { question_id: Number(questionId) } : {}) }))
      apply(view)
      void say(view.log[view.log.length - 1].text, view)
    } catch (e) {
      // UC3 4a: still no task after one retry, so stop (and switch the microphone off) and say practice is unavailable.
      void recorder.current?.stop(); recorder.current = null
      setError(`Speaking practice is temporarily unavailable: ${(e as Error).message}. Please try again later.`)
    } finally { setStarting(false) }
  }

  const startListening = () => {
    if (modeRef.current === 'server') { void startServerAnswer(); return }
    if (listener.current || !sessionRef.current) return
    stopSpeaking()
    textRef.current = { final: '', interim: '' }
    setCaption(''); setElapsed(0)
    started.current = Date.now()
    const current = sessionRef.current.ui.stage
    const cap = CAP[current] || 75
    const silence = SILENCE[current] || DEFAULT_SILENCE
    tickTimer.current = window.setInterval(() => {
      const secs = Math.round((Date.now() - started.current) / 1000)
      setElapsed(secs)
      if (secs >= cap) void finishAnswer()
    }, 500)
    setListening(true)
    listener.current = listen({
      onText: (final, interim) => {
        textRef.current = { final, interim }
        setCaption(`${final} ${interim}`.trim())
        window.clearTimeout(silenceTimer.current)
        silenceTimer.current = window.setTimeout(() => { if (`${textRef.current.final}${textRef.current.interim}`.trim() && Date.now() - started.current > MIN_ANSWER_MS) void finishAnswer() }, silence)
      },
      onError: message => {
        stopListening()
        // The browser's recognition runs on an online service; when it cannot be reached, switch to recognition on our server.
        if (/network|service-not-allowed|not available/i.test(message) && serverStt) {
          chooseMode('server'); setError('')
          notify("Your browser's speech service is unreachable, so answers are now recognised offline on the server.")
          void startServerAnswer()
          return
        }
        setError(message)
      },
    })
  }

  /* Server recognition: record until the learner pauses (or presses "I've finished"), then transcribe the whole answer. */
  const startServerAnswer = async () => {
    if (sttRecorder.current || !sessionRef.current) return
    stopSpeaking()
    const current = sessionRef.current.ui.stage
    const cap = CAP[current] || 75
    const silence = SILENCE[current] || DEFAULT_SILENCE
    let rec: { stop: () => Promise<Blob>; stream: MediaStream }
    try { rec = await recordMicrophone() } catch (e) { setError(`Microphone unavailable: ${(e as Error).message}. Allow microphone access or type your answer.`); return }
    sttRecorder.current = rec
    finishing.current = false
    started.current = Date.now()
    setCaption(''); setElapsed(0); setError(''); setListening(true)
    let heard = false, lastVoice = Date.now(), floor = 0.01
    stopLevel.current = monitorLevel(rec.stream, value => {
      setLevel(value)
      if (value > Math.max(0.02, floor * 2.5)) { heard = true; lastVoice = Date.now() }
      else if (!heard) floor = floor * .9 + value * .1 // learn the room's background noise before the learner starts
      if (heard && Date.now() - lastVoice > silence && Date.now() - started.current > MIN_ANSWER_MS) void finishServerAnswer()
    })
    tickTimer.current = window.setInterval(() => {
      const secs = Math.round((Date.now() - started.current) / 1000)
      setElapsed(secs)
      if (secs >= cap) void finishServerAnswer()
    }, 500)
  }
  const finishServerAnswer = async () => {
    if (!sttRecorder.current || finishing.current) return
    finishing.current = true
    const rec = sttRecorder.current
    const seconds = (Date.now() - started.current) / 1000
    stopLevel.current?.(); stopLevel.current = null
    window.clearInterval(tickTimer.current)
    const blob = await rec.stop()
    sttRecorder.current = null
    setListening(false); setLevel(0); setThinking(true)
    try {
      const text = (await transcribeOnServer(blob)).trim()
      setThinking(false)
      if (!text) { notify("I didn't catch that — please answer again.", 'error'); if (prefs.handsFree) void startServerAnswer(); return }
      await sendTurn(text, seconds)
    } catch (e) { setThinking(false); setError(`${(e as Error).message}. Try again or type your answer.`) }
  }
  const stopListening = () => {
    listener.current?.stop(); listener.current = null
    window.clearTimeout(silenceTimer.current); window.clearInterval(tickTimer.current)
    setListening(false)
  }

  const sendTurn = async (text: string, seconds: number) => {
    const view = sessionRef.current
    if (!view) return
    setThinking(true)
    try {
      const next = await post<SpeakingView>(`/speaking/sessions/${view.id}/turn`, { text, seconds })
      apply(next)
      setThinking(false)
      void say(next.reply || '', next)
    } catch (e) { setThinking(false); notify((e as Error).message, 'error'); if (prefs.handsFree && modeRef.current !== 'none') startListening() }
  }
  const finishAnswer = async () => {
    if (!listener.current) return
    const seconds = (Date.now() - started.current) / 1000
    const text = `${textRef.current.final} ${textRef.current.interim}`.trim()
    stopListening()
    setCaption('')
    if (!text) { notify("I didn't catch that — please try again.", 'error'); return }
    await sendTurn(text, seconds)
  }
  const sendTyped = async () => { const text = typed.trim(); if (!text) return; setTyped(''); await sendTurn(text, Math.max(5, text.split(/\s+/).length / 2.2)) }
  const startLongTurn = async () => {
    const view = sessionRef.current
    if (!view) return
    setPrep(false)
    setThinking(true)
    try { const next = await post<SpeakingView>(`/speaking/sessions/${view.id}/turn`, { event: 'ready' }); apply(next); setThinking(false); void say(next.reply || '', next) }
    catch (e) { setThinking(false); notify((e as Error).message, 'error') }
  }

  const finish = async () => {
    const view = sessionRef.current
    if (!view) return
    stopListening()
    stopLevel.current?.(); stopLevel.current = null
    if (sttRecorder.current) { void sttRecorder.current.stop(); sttRecorder.current = null }
    setThinking(true)
    try {
      const blob = await recorder.current?.stop()
      recorder.current = null
      if (blob && blob.size > 2000 && view.practice_id) {
        const body = new FormData(); body.append('file', blob, 'speaking-test.webm')
        await request(`/practice/${view.practice_id}/audio`, { method: 'POST', body }).catch(() => {})
      }
      const done = await post<SpeakingView>(`/speaking/sessions/${view.id}/finish`)
      apply(done)
      setMetrics(done.metrics || null)
      if (done.saved_to_mock) { notify('Speaking section saved to your mock exam'); onSaved?.() }
      if (done.result) { setResult(done.result); onResult?.(done.result) }
    } catch (e) { notify((e as Error).message, 'error') } finally { setThinking(false) }
  }

  const toggleHandsFree = () => { prefs.handsFree = !handsFree; setHandsFree(!handsFree) }
  const mood = moodFor(aiSpeaking, listening, thinking)
  const cue = session?.ui.cue_card
  const capFor = CAP[stage]
  const hideText = (item: { stage?: string; role: string }) => item.role === 'examiner' && item.stage === 'repeat' && session?.status === 'ACTIVE'

  if (!session) return <div className="panel panel-hot grid items-center gap-8 p-8 md:grid-cols-[auto_1fr]">
    <PixelAvatar persona={persona} mood="idle" size={170} />
    <div className="space-y-4">
      <span className="eyebrow">Live speaking examiner</span>
      <h2 className="heading text-3xl">Talk with {personaName(persona)}</h2>
      <p className="font-read text-mist">{personaName(persona)} runs a complete speaking test out loud: {mockId ? 'the speaking section of your mock exam' : 'IELTS Part 1 interview, Part 2 cue card (1 minute to prepare, 2 minutes to talk) and Part 3 discussion — or the TOEFL 2026 Listen & Repeat and Interview tasks'}. Answer with your microphone; your session is recorded for replay.</p>
      {mode === 'none' && <p className="tile font-read text-sm text-sun">Speech recognition is not available here, so please type your answers. (Ask your teacher to enable server speech recognition.)</p>}
      {error && <p role="alert" className="font-read text-rose">{error}</p>}
      <button className="btn-primary" disabled={starting} onClick={begin}><Play size={17} /> {starting ? 'Starting…' : 'Start speaking test'}</button>
    </div>
  </div>

  return <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
    <aside className="panel panel-hot flex flex-col items-center gap-4 p-6 lg:sticky lg:top-24 lg:self-start">
      <PixelAvatar persona={persona} mood={mood} size={190} />
      <div className="text-center"><p className="font-arcade text-[11px] text-magenta">{session.ui.part}</p>{session.ui.progress && <p className="mt-2 font-pixel text-mist">{session.ui.progress}</p>}</div>
      {listening && <div className="w-full text-center"><p className="font-pixel text-cyan">Listening…</p><p className="num text-4xl text-cyan">{capFor ? clock(Math.max(0, capFor - elapsed)) : clock(elapsed)}</p>
        {mode === 'server' && <><div className="mx-auto mt-2 h-2 w-40 bg-abyss" aria-label="Microphone level"><div className="h-2 bg-lime transition-[width] duration-100" style={{ width: `${Math.min(100, Math.round(level * 900))}%` }} /></div>
          <p className="mt-2 font-read text-xs text-mist">Speak naturally. Your answer is sent after a pause of {Math.round((SILENCE[stage] || DEFAULT_SILENCE) / 1000)} seconds, or press “I've finished”.</p></>}</div>}
      {stage === 'p2_talk' && !listening && <p className="font-read text-xs text-mist">Speak for up to two minutes.</p>}
      {session.status === 'ACTIVE' && !prep && <div className="flex w-full flex-col gap-2">
        {mode !== 'none' && (listening
          ? <button className="btn-danger" onClick={() => void (mode === 'server' ? finishServerAnswer() : finishAnswer())}><Square size={16} /> I've finished</button>
          : <button className="btn-cyan" disabled={aiSpeaking || thinking} onClick={startListening}><Mic size={17} /> Answer</button>)}
        {!mockId && lastExaminer && !hideText(lastExaminer) && <button className="btn-secondary" disabled={aiSpeaking || listening} onClick={() => speak(lastExaminer.text, persona, { force: true })}><Volume2 size={16} /> Repeat question</button>}
        <button className="btn-ghost justify-center" onClick={toggleHandsFree}>{handsFree ? <Mic size={14} /> : <MicOff size={14} />} Hands-free {handsFree ? 'on' : 'off'}</button>
      </div>}
      {session.status === 'FINISHED' && !result && !session.saved_to_mock && <button className="btn-primary" disabled={thinking} onClick={finish}>Get my feedback</button>}
      {(result || session.saved_to_mock) && !mockId && <button className="btn-sun" onClick={() => { setSession(null); sessionRef.current = null; setResult(null) }}><RotateCcw size={16} /> New test</button>}
    </aside>

    <section className="space-y-5">
      {prep && cue && <div className="panel panel-sun space-y-4 p-6 anim-rise">
        <div className="flex flex-wrap items-center justify-between gap-3"><span className="eyebrow">Part 2 · cue card</span><span className="font-pixel">Preparation <Countdown seconds={60} running={prep} className="text-4xl" onDone={startLongTurn} /></span></div>
        <p className="font-pixel text-2xl text-moon">{cue.cue}</p>
        <p className="font-read text-mist">You should say:</p>
        <ul className="space-y-1 font-read">{cue.bullets.map(b => <li key={b}>▸ {b}</li>)}</ul>
        <textarea className="input min-h-24" placeholder="Notes (only you see these)…" aria-label="Preparation notes" />
        <button className="btn-primary" onClick={startLongTurn}><Mic size={16} /> I'm ready — start my 2 minutes</button>
      </div>}
      {!prep && cue && stage.startsWith('p2') && <div className="panel panel-flat p-4 font-read text-sm"><b className="font-pixel text-sun">Cue card:</b> {cue.cue} {cue.bullets.join(' · ')}</div>}

      <div className="panel p-5" aria-live="polite">
        <div className="max-h-[52vh] space-y-3 overflow-y-auto pr-1">
          {session.log.map((item, i) => <div key={i} className={`flex ${item.role === 'learner' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] px-4 py-2.5 font-read text-[15px] leading-6 ${item.role === 'learner' ? 'bg-violet text-moon' : 'bg-abyss/80 text-moon'}`} style={{ boxShadow: `0 0 0 2px ${item.role === 'learner' ? '#ff4fd8' : '#3ef0ff'}` }}>
              <span className="mb-1 block font-pixel text-xs uppercase tracking-wider text-mist">{item.role === 'learner' ? `You${item.seconds ? ` · ${Math.round(item.seconds)}s` : ''}` : `${personaName(persona)} · ${item.part}`}{item.follow_up ? ' · follow-up' : ''}</span>
              {hideText(item) ? <span className="italic text-mist">🔊 Listen and repeat — the sentence is spoken only.</span> : item.text}
              {item.repeat_accuracy !== undefined && session.status !== 'ACTIVE' && <span className="mt-1 block text-xs text-lime">Repeat accuracy {Math.round(item.repeat_accuracy * 100)}% {item.repeat_target ? `· target: “${item.repeat_target}”` : ''}</span>}
            </div>
          </div>)}
          {caption && <div className="flex justify-end"><div className="caret max-w-[85%] bg-violet/40 px-4 py-2.5 font-read text-moon/80" style={{ boxShadow: '0 0 0 2px #ff4fd8' }}>{caption}</div></div>}
          {thinking && <p className="font-pixel text-mist">{personaName(persona)} is thinking…</p>}
        </div>
        {session.status === 'ACTIVE' && !prep && <form className="mt-4 flex gap-2" onSubmit={e => { e.preventDefault(); void sendTyped() }}>
          <Keyboard size={18} className="mt-3 shrink-0 text-fog" />
          <input aria-label="Type your answer" className="input" value={typed} onChange={e => setTyped(e.target.value)} placeholder="…or type your answer here" disabled={listening || thinking} />
          <button className="btn-secondary" disabled={!typed.trim() || thinking}>Send</button>
        </form>}
        {error && <p role="alert" className="mt-3 font-read text-sm text-rose">{error}</p>}
      </div>

      {metrics && <div className="flex flex-wrap gap-2">{Object.entries(metrics).map(([k, v]) => <span key={k} className="pill text-cyan">{k.replaceAll('_', ' ')}: {v}</span>)}</div>}
      {session.saved_to_mock && <div className="panel panel-lime p-5 font-pixel text-lime">Speaking section saved. Scores are calculated when you submit the whole mock exam.</div>}
      <FeedbackPanel result={result} />
    </section>
  </div>
}

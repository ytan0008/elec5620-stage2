import { useEffect, useRef, useState } from 'react'
import { Keyboard, Mic, MicOff, Play, RotateCcw, Square, Volume2 } from 'lucide-react'
import { Result, SpeakingView, health, post, request } from '../api'
import { PixelAvatar, personaName } from '../pixel/Avatar'
import { moodFor, usePersona } from '../persona'
import { Listener, listen, prefs, recognitionSupported, recordMicrophone, speak, stopSpeaking, transcribeOnServer } from '../voice'
import { Countdown, FeedbackPanel, Notify, clock } from '../ui'

type Props = { notify: Notify; mockId?: number; questionId?: string | null; onSaved?: () => void; onResult?: (result: Result) => void }
const SILENCE: Record<string, number> = { p2_talk: 6500, repeat: 2200, interview: 4000 }
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
  const [error, setError] = useState('')
  const sessionRef = useRef<SpeakingView | null>(null)
  const listener = useRef<Listener | null>(null)
  const textRef = useRef({ final: '', interim: '' })
  const started = useRef(0)
  const silenceTimer = useRef(0)
  const tickTimer = useRef(0)
  const recorder = useRef<{ stop: () => Promise<Blob> } | null>(null)
  const sttRecorder = useRef<{ stop: () => Promise<Blob> } | null>(null)
  const alive = useRef(true)
  const supported = recognitionSupported()

  useEffect(() => { health().then(h => setServerStt(h.server_stt)).catch(() => {}) }, [])
  useEffect(() => () => { alive.current = false; listener.current?.abort(); stopSpeaking(); window.clearTimeout(silenceTimer.current); window.clearInterval(tickTimer.current); void recorder.current?.stop() }, [])

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
    if (prefs.handsFree && supported) startListening()
  }

  const begin = async () => {
    setError(''); setResult(null)
    try { recorder.current = await recordMicrophone() } catch { recorder.current = null }
    try {
      const view = await post<SpeakingView>('/speaking/sessions', { persona, ...(mockId ? { mock_id: mockId } : {}), ...(questionId ? { question_id: Number(questionId) } : {}) })
      apply(view)
      void say(view.log[view.log.length - 1].text, view)
    } catch (e) { setError((e as Error).message) }
  }

  const startListening = () => {
    if (listener.current || !sessionRef.current) return
    stopSpeaking()
    textRef.current = { final: '', interim: '' }
    setCaption(''); setElapsed(0)
    started.current = Date.now()
    const current = sessionRef.current.ui.stage
    const cap = CAP[current] || 75
    const silence = SILENCE[current] || 2600
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
        silenceTimer.current = window.setTimeout(() => { if (`${textRef.current.final}${textRef.current.interim}`.trim()) void finishAnswer() }, silence)
      },
      onError: message => { setError(message); stopListening() },
    })
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
    } catch (e) { setThinking(false); notify((e as Error).message, 'error'); if (prefs.handsFree && supported) startListening() }
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
  const serverRecord = async () => {
    if (sttRecorder.current) {
      const blob = await sttRecorder.current.stop(); sttRecorder.current = null; setListening(false)
      const seconds = (Date.now() - started.current) / 1000
      setThinking(true)
      try { const text = await transcribeOnServer(blob); setThinking(false); await sendTurn(text, seconds) } catch (e) { setThinking(false); notify((e as Error).message, 'error') }
      return
    }
    try { sttRecorder.current = await recordMicrophone(); started.current = Date.now(); setListening(true) } catch (e) { notify(`Microphone unavailable: ${(e as Error).message}`, 'error') }
  }
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
      {!supported && <p className="tile font-read text-sm text-sun">This browser has no built-in speech recognition. {serverStt ? 'Use the record button (cloud transcription) or type your answers.' : 'Use Chrome or Edge for voice, or type your answers.'}</p>}
      {error && <p role="alert" className="font-read text-rose">{error}</p>}
      <button className="btn-primary" onClick={begin}><Play size={17} /> Start speaking test</button>
    </div>
  </div>

  return <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
    <aside className="panel panel-hot flex flex-col items-center gap-4 p-6 lg:sticky lg:top-24 lg:self-start">
      <PixelAvatar persona={persona} mood={mood} size={190} />
      <div className="text-center"><p className="font-arcade text-[11px] text-magenta">{session.ui.part}</p>{session.ui.progress && <p className="mt-2 font-pixel text-mist">{session.ui.progress}</p>}</div>
      {listening && <div className="text-center"><p className="font-pixel text-cyan">Listening…</p><p className="num text-4xl text-cyan">{capFor ? clock(Math.max(0, capFor - elapsed)) : clock(elapsed)}</p></div>}
      {stage === 'p2_talk' && !listening && <p className="font-read text-xs text-mist">Speak for up to two minutes.</p>}
      {session.status === 'ACTIVE' && !prep && <div className="flex w-full flex-col gap-2">
        {supported ? (listening
          ? <button className="btn-danger" onClick={finishAnswer}><Square size={16} /> I've finished</button>
          : <button className="btn-cyan" disabled={aiSpeaking || thinking} onClick={startListening}><Mic size={17} /> Answer</button>)
          : serverStt && <button className={sttRecorder.current ? 'btn-danger' : 'btn-cyan'} disabled={aiSpeaking || thinking} onClick={serverRecord}>{sttRecorder.current ? <><Square size={16} /> Stop & send</> : <><Mic size={17} /> Record answer</>}</button>}
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

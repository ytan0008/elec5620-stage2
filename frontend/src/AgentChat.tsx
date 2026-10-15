import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Mic, Send, Volume2, VolumeX, X } from 'lucide-react'
import { ChatEvent, ChatMessage, notebookChanged, post, request } from './api'
import { PixelAvatar, personaName } from './pixel/Avatar'
import { moodFor, usePersona } from './persona'
import { useIsExamLocked } from './examLock'
import ReportProblem from './ReportProblem'
import { Listener, listen, prefs, recognitionSupported, speak, stopSpeaking } from './voice'

type Conversation = { agent: string; context: string; mode: string; messages: ChatMessage[]; events?: ChatEvent[] }

function contextFor(path: string) {
  if (path.startsWith('/practice/')) return path.split('/')[2]
  return ({ '/plans': 'plan', '/profile': 'profile', '/dashboard': 'dashboard', '/questions': 'questions', '/materials': 'materials', '/analytics': 'analytics', '/knowledge': 'knowledge', '/portrait': 'portrait', '/workflow': 'workflow', '/settings': 'settings', '/notebook': 'notebook' } as Record<string, string>)[path] || 'dashboard'
}

function Typewriter({ text, animate }: { text: string; animate: boolean }) {
  const [shown, setShown] = useState(animate ? 0 : text.length)
  useEffect(() => {
    if (!animate) { setShown(text.length); return }
    setShown(0)
    const id = window.setInterval(() => setShown(value => { if (value >= text.length) { window.clearInterval(id); return value } return value + 2 }), 18)
    return () => window.clearInterval(id)
  }, [text, animate])
  return <span className={shown < text.length ? 'caret' : ''}>{text.slice(0, shown)}</span>
}

export default function AgentChat() {
  const location = useLocation()
  const context = contextFor(location.pathname)
  const { persona, aiSpeaking } = usePersona()
  const [open, setOpen] = useState(false)
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [listening, setListening] = useState(false)
  const [voiceOn, setVoiceOn] = useState(!prefs.muted)
  const [fresh, setFresh] = useState(-1)
  const [notes, setNotes] = useState<string[]>([])
  const examLocked = useIsExamLocked()
  const listener = useRef<Listener | null>(null)
  const bottom = useRef<HTMLDivElement | null>(null)
  useEffect(() => { setError(''); setDraft(''); request<Conversation>(`/chat/${context}`).then(setConversation).catch(e => setError(e.message)) }, [context])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [conversation?.messages.length, open])
  useEffect(() => () => { listener.current?.abort() }, [context])
  const sendRef = useRef<(value: string) => void>(() => {})
  useEffect(() => {
    const onAsk = (event: Event) => { setOpen(true); sendRef.current((event as CustomEvent<string>).detail) }
    window.addEventListener('ask-tutor', onAsk)
    return () => window.removeEventListener('ask-tutor', onAsk)
  }, [])
  if (examLocked || ['/mock', '/onboarding', '/tutor'].includes(location.pathname) || location.pathname === '/practice/speaking') return null

  const send = async (value = draft) => {
    const message = value.trim()
    if (!message || busy) return
    setBusy(true); setError(''); setDraft('')
    try {
      const next = await post<Conversation>(`/chat/${context}`, { message, persona })
      setConversation(next)
      setFresh(next.messages.length - 1)
      const saved = (next.events || []).map(e => e.type === 'word' ? `📒 Word book: ${e.word}` : e.type === 'memory' ? `🧠 Remembered: ${e.text}` : e.remembered ? `✓ Quiz: ${e.word}` : `↺ Quiz: review ${e.word} again`)
      setNotes(saved)
      if ((next.events || []).some(e => e.type !== 'memory')) notebookChanged()
      if (voiceOn) void speak(next.messages[next.messages.length - 1].text, persona)
    } catch (e) { setDraft(message); setError((e as Error).message) } finally { setBusy(false) }
  }
  sendRef.current = value => { void send(value) }
  const mic = () => {
    if (listening) { listener.current?.stop(); return }
    stopSpeaking()
    let latest = ''
    let timer = 0
    setListening(true)
    listener.current = listen({
      onText: (final, interim) => { latest = `${final} ${interim}`.trim(); setDraft(latest); window.clearTimeout(timer); timer = window.setTimeout(() => { listener.current?.stop() }, 1800) },
      onError: message => { setError(message); setListening(false) },
      onEnd: () => { setListening(false); listener.current = null; if (latest) void send(latest) },
    })
  }
  const toggleVoice = () => { const next = !voiceOn; setVoiceOn(next); prefs.muted = !next; if (!next) stopSpeaking() }
  const agent = conversation?.agent || 'Learning Coordinator'
  const name = personaName(persona)

  return <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end gap-3">
    {open && <section className="panel panel-hot flex h-[min(600px,76vh)] w-[min(400px,calc(100vw-32px))] flex-col !m-0" aria-label={`${agent} conversation`}>
      <header className="flex items-center gap-3 bg-plum/90 px-3 py-2">
        <PixelAvatar persona={persona} mood={moodFor(aiSpeaking, listening, busy)} size={44} />
        <div className="min-w-0 flex-1"><div className="font-pixel text-lg leading-tight">{name} <span className="text-sm text-mist">· {agent}</span></div><div className="font-pixel text-xs uppercase text-cyan">{conversation?.mode === 'REAL' ? 'cloud AI' : 'built-in tutor'} · {context}</div></div>
        <button onClick={toggleVoice} aria-label={voiceOn ? 'Mute spoken replies' : 'Speak replies aloud'} className="p-1 text-cyan">{voiceOn ? <Volume2 size={19} /> : <VolumeX size={19} />}</button>
        <button onClick={() => setOpen(false)} aria-label="Close agent chat" className="p-1"><X size={19} /></button>
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
        {!conversation?.messages.length && <div className="tile font-read text-sm text-mist">Hi, I'm {name}! Ask me about strategies, question types, vocabulary or your plan. I remember what you tell me. Type <b>check: your sentence</b> to find mistakes, tell me a word you don't know to save it, or say <b>quiz me</b>.</div>}
        {conversation?.messages.map((item, i) => <div key={i} className={`flex ${item.role === 'learner' ? 'justify-end' : 'justify-start'}`}>
          <div className={`max-w-[88%] px-3 py-2 font-read text-sm leading-relaxed ${item.role === 'learner' ? 'bg-violet' : 'bg-abyss/80'}`} style={{ boxShadow: `0 0 0 2px ${item.role === 'learner' ? '#ff4fd8' : '#3ef0ff'}` }}>
            {item.role === 'learner' ? item.text : <Typewriter text={item.text} animate={i === fresh} />}
            {item.role !== 'learner' && <button onClick={() => speak(item.text, persona, { force: true })} aria-label="Read reply aloud" className="mt-1 flex items-center gap-1 font-pixel text-xs text-cyan"><Volume2 size={13} /> listen</button>}
          </div>
        </div>)}
        {notes.length > 0 && !busy && <div className="flex flex-wrap gap-1">{notes.map(note => <span key={note} className="pill text-lime">{note}</span>)}</div>}
        {busy && <p className="font-pixel text-sm text-mist">{name} is thinking…</p>}
        {(conversation?.messages.length || 0) > 0 && <ReportProblem category="tutor" context={{ chat: context }} label="Tutor said something wrong?" />}
        <div ref={bottom} />
      </div>
      {error && <p role="alert" className="mx-4 mb-2 font-read text-xs text-rose">{error}</p>}
      <form onSubmit={event => { event.preventDefault(); void send() }} className="flex items-center gap-2 border-t-4 border-plum p-3">
        <input aria-label="Message agent" className="input min-w-0 flex-1 !py-2" value={draft} maxLength={2000} onChange={event => setDraft(event.target.value)} placeholder={listening ? 'Listening…' : `Message ${name}…`} />
        {recognitionSupported() && <button type="button" onClick={mic} aria-label={listening ? 'Stop voice input' : 'Start voice input'} className={`p-2 ${listening ? 'bg-rose text-night' : 'bg-plum text-cyan'}`} style={{ boxShadow: '0 0 0 2px #6b52d6' }}><Mic size={18} /></button>}
        <button type="submit" disabled={busy || !draft.trim()} aria-label="Send agent message" className="bg-magenta p-2 text-night" style={{ boxShadow: '0 0 0 2px #140c2e' }}><Send size={18} /></button>
      </form>
    </section>}
    <button data-tutor-launcher onClick={() => setOpen(value => !value)} aria-label={open ? 'Hide agent assistant' : 'Open agent assistant'} className="group relative flex items-end gap-2">
      {!open && <span className="panel panel-flat !m-0 mb-6 hidden px-3 py-1.5 font-pixel text-sm sm:block">Ask {name}</span>}
      <PixelAvatar persona={persona} mood={moodFor(aiSpeaking && open, listening, busy)} size={72} />
    </button>
  </div>
}

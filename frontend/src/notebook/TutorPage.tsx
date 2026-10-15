import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Brain, Mic, Plus, Send, Sparkles, Square, Trash2, Volume2 } from 'lucide-react'
import { ChatEvent, ChatMessage, Memory, NotebookStats, notebookChanged, post, request } from '../api'
import { PixelAvatar, personaName } from '../pixel/Avatar'
import { moodFor, usePersona } from '../persona'
import { Listener, listen, prefs, recognitionSupported, speak, stopSpeaking } from '../voice'
import { Notify, PageTitle, nice } from '../ui'

const KIND_COLOR: Record<string, string> = { about: 'text-cyan', goal: 'text-lime', preference: 'text-sun', difficulty: 'text-rose', progress: 'text-magenta', note: 'text-mist' }
const STARTERS = ['Coach me for today', 'What are my weak points?', 'Quiz me', 'Explain the difference between affect and effect', 'How do I get band 7 in Writing Task 2?', 'What do you remember about me?']

export default function TutorPage({ notify }: { notify: Notify }) {
  const { persona, aiSpeaking } = usePersona()
  const name = personaName(persona)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [memory, setMemory] = useState<Memory[]>([])
  const [stats, setStats] = useState<NotebookStats | null>(null)
  const [draft, setDraft] = useState('')
  const [newMemory, setNewMemory] = useState('')
  const [busy, setBusy] = useState(false)
  const [listening, setListening] = useState(false)
  const [voiceOn, setVoiceOn] = useState(!prefs.muted)
  const listener = useRef<Listener | null>(null)
  const bottom = useRef<HTMLDivElement | null>(null)

  const loadSide = () => {
    request<Memory[]>('/tutor/memory').then(setMemory).catch(() => {})
    request<NotebookStats>('/notebook/stats').then(setStats).catch(() => {})
  }
  useEffect(() => {
    request<{ messages: ChatMessage[] }>('/chat/tutor').then(c => setMessages(c.messages)).catch(e => notify(e.message, 'error'))
    loadSide()
    return () => { listener.current?.abort(); stopSpeaking() }
  }, [])
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'nearest' }) }, [messages.length, busy])

  const reportEvents = (events: ChatEvent[] = []) => {
    for (const event of events) {
      if (event.type === 'word') notify(`📒 “${event.word}” ${event.created ? 'saved to your Word book' : 'is already in your Word book'}`)
      if (event.type === 'memory') notify(`🧠 ${name} will remember: ${event.text}`)
    }
    if (events.length) { notebookChanged(); loadSide() }
  }
  const send = async (value: string) => {
    const message = value.trim()
    if (!message || busy) return
    if (/^coach me/i.test(message)) return coach()
    setBusy(true); setDraft('')
    setMessages(previous => [...previous, { role: 'learner', text: message }])
    try {
      const next = await post<{ messages: ChatMessage[]; events: ChatEvent[] }>('/chat/tutor', { message, persona })
      setMessages(next.messages)
      reportEvents(next.events)
      if (voiceOn) void speak(next.messages[next.messages.length - 1].text, persona)
    } catch (e) { notify((e as Error).message, 'error'); setDraft(message) } finally { setBusy(false) }
  }
  const coach = async () => {
    setBusy(true)
    try {
      const result = await post<{ message: string; messages: ChatMessage[] }>(`/tutor/coach?persona=${persona}`)
      setMessages(result.messages)
      if (voiceOn) void speak(result.message, persona)
    } catch (e) { notify((e as Error).message, 'error') } finally { setBusy(false) }
  }
  const mic = () => {
    if (listening) { listener.current?.stop(); return }
    stopSpeaking()
    let text = ''
    let timer = 0
    setListening(true)
    listener.current = listen({
      onText: (final, interim) => { text = `${final} ${interim}`.trim(); setDraft(text); window.clearTimeout(timer); timer = window.setTimeout(() => listener.current?.stop(), 2000) },
      onError: message => { notify(message, 'error'); setListening(false) },
      onEnd: () => { setListening(false); listener.current = null; if (text) void send(text) },
    })
  }
  const addMemory = async () => {
    if (newMemory.trim().length < 2) return
    try { await post('/tutor/memory', { kind: 'note', text: newMemory.trim() }); setNewMemory(''); loadSide(); notify(`${name} will remember that`) } catch (e) { notify((e as Error).message, 'error') }
  }
  const forget = async (item: Memory) => {
    try { await request(`/tutor/memory/${item.id}`, { method: 'DELETE' }); setMemory(previous => previous.filter(m => m.id !== item.id)) } catch (e) { notify((e as Error).message, 'error') }
  }

  return <>
    <PageTitle eyebrow="AI Tutor · long-term memory" title={`Study with ${name}`}
      subtitle={`${name} remembers your goals, difficulties and progress across every session, reads your mistake, word and grammar books, and guides you step by step. Tell ${name} any word you don't know and it goes straight into your Word book.`}
      action={<button className="btn-primary" disabled={busy} onClick={coach}><Sparkles size={16} /> Coach me</button>} />
    <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
      <section className="panel panel-hot flex min-h-[620px] flex-col p-0">
        <div className="flex items-center gap-4 border-b-4 border-plum p-4">
          <PixelAvatar persona={persona} mood={moodFor(aiSpeaking, listening, busy)} size={84} />
          <div className="min-w-0 flex-1"><p className="font-pixel text-2xl">{name}</p><p className="font-read text-sm text-mist">Remembers {memory.length} thing{memory.length === 1 ? '' : 's'} about you · {stats ? `${stats.counts.mistake.active} open mistakes · ${stats.due_words} words due` : '…'}</p></div>
          <button className="btn-secondary !px-2" onClick={() => { setVoiceOn(!voiceOn); prefs.muted = voiceOn; if (voiceOn) stopSpeaking() }} aria-label={voiceOn ? 'Mute voice' : 'Speak replies'}><Volume2 size={17} className={voiceOn ? 'text-cyan' : 'text-fog'} /></button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-5" style={{ maxHeight: '58vh' }} aria-live="polite">
          {!messages.length && <div className="tile font-read text-mist">Hi! I'm {name}. Tell me about yourself and your goals — I'll remember. Or try one of the suggestions below.</div>}
          {messages.map((m, i) => <div key={i} className={`flex ${m.role === 'learner' ? 'justify-end' : ''}`}>
            <div className={`max-w-[85%] whitespace-pre-line px-4 py-2.5 font-read leading-relaxed ${m.role === 'learner' ? 'bg-violet' : m.coach ? 'bg-plum' : 'bg-abyss/80'}`} style={{ boxShadow: `0 0 0 2px ${m.role === 'learner' ? '#ff4fd8' : m.coach ? '#ffd34d' : '#3ef0ff'}` }}>
              {m.coach && <span className="mb-1 block font-pixel text-xs uppercase text-sun">✦ Coaching plan</span>}
              {m.text}
              {m.role !== 'learner' && <button className="mt-1 flex items-center gap-1 font-pixel text-xs text-cyan" onClick={() => speak(m.text, persona, { force: true })}><Volume2 size={13} /> listen</button>}
            </div>
          </div>)}
          {busy && <p className="font-pixel text-mist">{name} is thinking…</p>}
          <div ref={bottom} />
        </div>
        <div className="flex flex-wrap gap-1 px-4">{STARTERS.map(s => <button key={s} disabled={busy} onClick={() => send(s)} className="btn-secondary !py-1 text-xs normal-case">{s}</button>)}</div>
        <form className="flex gap-2 p-4" onSubmit={e => { e.preventDefault(); void send(draft) }}>
          <input aria-label="Message your tutor" className="input" value={draft} onChange={e => setDraft(e.target.value)} placeholder={listening ? 'Listening…' : 'Ask anything, e.g. “I don’t know the word ‘mitigate’”'} />
          {recognitionSupported() && <button type="button" onClick={mic} aria-label={listening ? 'Stop voice input' : 'Speak to tutor'} className={listening ? 'btn-danger !px-3' : 'btn-cyan !px-3'}>{listening ? <Square size={17} /> : <Mic size={17} />}</button>}
          <button className="btn-primary !px-3" disabled={busy || !draft.trim()} aria-label="Send to tutor"><Send size={17} /></button>
        </form>
      </section>

      <aside className="space-y-5">
        <div className="panel panel-cyan p-5">
          <h2 className="flex items-center gap-2 section-title"><Brain size={19} className="text-cyan" /> {name}'s memory</h2>
          <p className="mt-1 font-read text-xs text-mist">Learned from your chats and verified results. Delete anything that's wrong.</p>
          <div className="mt-4 max-h-80 space-y-2 overflow-y-auto pr-1">
            {!memory.length && <p className="font-read text-sm text-fog">Nothing yet. Try “My name is … and I find listening to numbers hard.”</p>}
            {memory.map(item => <div key={item.id} className="tile flex items-start gap-2 font-read text-sm">
              <span className={`pill shrink-0 !text-[10px] ${KIND_COLOR[item.kind] || 'text-mist'}`}>{item.kind}</span>
              <span className="min-w-0 flex-1">{item.text}</span>
              <button onClick={() => forget(item)} aria-label={`Forget ${item.text}`} className="shrink-0 text-fog hover:text-rose"><Trash2 size={14} /></button>
            </div>)}
          </div>
          <form className="mt-3 flex gap-2" onSubmit={e => { e.preventDefault(); void addMemory() }}>
            <input aria-label="Add a memory" className="input !py-1.5 text-sm" value={newMemory} onChange={e => setNewMemory(e.target.value)} placeholder="Tell it something to remember" />
            <button className="btn-secondary !px-2" aria-label="Save memory"><Plus size={16} /></button>
          </form>
        </div>
        {stats && <div className="panel p-5">
          <h2 className="section-title">Your notebooks</h2>
          <div className="mt-3 grid grid-cols-2 gap-2">{([['mistake', 'Mistakes', 'text-rose'], ['word', 'Words', 'text-cyan'], ['grammar', 'Grammar', 'text-sun'], ['sentence', 'Sentences', 'text-lime']] as const).map(([kind, label, color]) =>
            <Link key={kind} to={`/notebook?tab=${kind}`} className="tile text-center hover:bg-plum"><span className={`num text-4xl ${color}`}>{stats.counts[kind]?.active ?? 0}</span><p className="font-pixel text-xs uppercase text-mist">{label}</p></Link>)}</div>
          {stats.mistakes_by_type[0] && <p className="mt-3 font-read text-sm text-mist">Most missed: <b className="text-moon">{stats.mistakes_by_type[0].name}</b></p>}
          {stats.grammar_issues[0] && <p className="font-read text-sm text-mist">Top grammar slip: <b className="text-moon">{nice(stats.grammar_issues[0].name)}</b></p>}
          <Link to="/notebook" className="btn-ghost mt-2 !px-0">Open notebooks →</Link>
        </div>}
      </aside>
    </div>
  </>
}

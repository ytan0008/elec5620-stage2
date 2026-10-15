import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Mic, Send, Square } from 'lucide-react'
import { post, request } from '../api'
import { PixelAvatar, personaName } from '../pixel/Avatar'
import { moodFor, usePersona } from '../persona'
import { Listener, listen, recognitionSupported, speak, stopSpeaking } from '../voice'
import { Notify, PageTitle } from '../ui'
import SpeakingStudio from './SpeakingStudio'

type Message = { role: string; text: string }

function FreeTalk({ notify }: { notify: Notify }) {
  const { persona, aiSpeaking } = usePersona()
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [caption, setCaption] = useState('')
  const [listening, setListening] = useState(false)
  const [thinking, setThinking] = useState(false)
  const [loop, setLoop] = useState(false)
  const listener = useRef<Listener | null>(null)
  const textRef = useRef('')
  const silence = useRef(0)
  const loopRef = useRef(false)
  const bottom = useRef<HTMLDivElement | null>(null)
  useEffect(() => { request<{ messages: Message[] }>('/chat/speaking').then(c => setMessages(c.messages)).catch(() => {}) ; return () => { listener.current?.abort(); stopSpeaking() } }, [])
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'nearest' }) }, [messages.length, caption])

  const send = async (text: string) => {
    if (!text.trim()) return
    setThinking(true)
    try {
      const next = await post<{ messages: Message[] }>('/chat/speaking', { message: text.trim(), persona })
      setMessages(next.messages)
      setThinking(false)
      await speak(next.messages[next.messages.length - 1].text, persona, { force: true })
      if (loopRef.current) start()
    } catch (e) { setThinking(false); notify((e as Error).message, 'error') }
  }
  const stop = (submit: boolean) => {
    listener.current?.stop(); listener.current = null; window.clearTimeout(silence.current); setListening(false)
    const text = textRef.current.trim(); textRef.current = ''; setCaption('')
    if (submit && text) void send(text)
  }
  const start = () => {
    if (listener.current) return
    stopSpeaking(); textRef.current = ''; setListening(true)
    listener.current = listen({
      onText: (final, interim) => { textRef.current = `${final} ${interim}`; setCaption(textRef.current.trim()); window.clearTimeout(silence.current); silence.current = window.setTimeout(() => stop(true), 2400) },
      onError: message => { notify(message, 'error'); loopRef.current = false; setLoop(false); stop(false) },
    })
  }
  const toggleLoop = () => { const next = !loop; loopRef.current = next; setLoop(next); if (next) start(); else stop(false) }

  return <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
    <aside className="panel panel-cyan flex flex-col items-center gap-4 p-6 lg:self-start">
      <PixelAvatar persona={persona} mood={moodFor(aiSpeaking, listening, thinking)} size={170} />
      <p className="text-center font-read text-sm text-mist">Chat freely with {personaName(persona)}. You get gentle corrections and follow-up questions, spoken aloud.</p>
      {recognitionSupported() ? <button className={loop ? 'btn-danger w-full' : 'btn-cyan w-full'} onClick={toggleLoop}>{loop ? <><Square size={16} /> End conversation</> : <><Mic size={17} /> Start talking</>}</button>
        : <p className="tile font-read text-xs text-sun">Voice input needs Chrome or Edge. You can still type and hear replies.</p>}
    </aside>
    <div className="panel flex min-h-[460px] flex-col p-5">
      <div className="flex-1 space-y-3 overflow-y-auto pr-1" aria-live="polite">
        {!messages.length && <p className="tile font-read text-mist">Say “hello” or ask {personaName(persona)} for a topic to get started.</p>}
        {messages.map((m, i) => <div key={i} className={`flex ${m.role === 'learner' ? 'justify-end' : ''}`}><div className={`max-w-[85%] px-4 py-2 font-read ${m.role === 'learner' ? 'bg-violet' : 'bg-abyss/80'}`} style={{ boxShadow: `0 0 0 2px ${m.role === 'learner' ? '#ff4fd8' : '#3ef0ff'}` }}>
          {m.text}{m.role !== 'learner' && <button className="ml-2 align-middle text-cyan" aria-label="Play reply" onClick={() => speak(m.text, persona, { force: true })}>🔊</button>}
        </div></div>)}
        {caption && <div className="flex justify-end"><div className="caret bg-violet/40 px-4 py-2 font-read">{caption}</div></div>}
        {thinking && <p className="font-pixel text-mist">{personaName(persona)} is thinking…</p>}
        <div ref={bottom} />
      </div>
      <form className="mt-4 flex gap-2" onSubmit={e => { e.preventDefault(); const t = draft; setDraft(''); void send(t) }}>
        <input aria-label="Message" className="input" value={draft} onChange={e => setDraft(e.target.value)} placeholder="Type a message…" />
        <button className="btn-primary !px-3" aria-label="Send message" disabled={!draft.trim() || thinking}><Send size={17} /></button>
      </form>
    </div>
  </div>
}

export default function SpeakingPage({ notify }: { notify: Notify }) {
  const [params] = useSearchParams()
  const [tab, setTab] = useState<'test' | 'talk'>('test')
  return <>
    <PageTitle eyebrow="Speaking · AI examiner" title="Speaking room" subtitle="A real-format speaking test, spoken aloud by your pixel examiner, with feedback on fluency, vocabulary and grammar — or relaxed free conversation practice."
      action={<div className="flex gap-1">{([['test', 'Speaking test'], ['talk', 'Free talk']] as const).map(([key, label]) => <button key={key} onClick={() => setTab(key)} className={tab === key ? 'btn-primary' : 'btn-secondary'}>{label}</button>)}</div>} />
    {tab === 'test' ? <SpeakingStudio notify={notify} questionId={params.get('question')} /> : <FreeTalk notify={notify} />}
  </>
}

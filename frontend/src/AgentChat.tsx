import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Bot, Mic, Send, Volume2, X } from 'lucide-react'
import { post, request } from './api'

type Conversation={agent:string;context:string;mode:string;messages:{role:string;text:string}[]}
type Recognition={lang:string;interimResults:boolean;onresult:((event:any)=>void)|null;onerror:((event:any)=>void)|null;onend:(()=>void)|null;start:()=>void;stop:()=>void}

function contextFor(path:string){
  if(path.startsWith('/practice/'))return path.split('/')[2]
  return ({'/plans':'plan','/profile':'profile','/dashboard':'dashboard','/questions':'questions','/materials':'materials','/analytics':'analytics','/knowledge':'knowledge','/portrait':'portrait','/workflow':'workflow','/settings':'settings'} as Record<string,string>)[path]||'dashboard'
}

export default function AgentChat(){
  const location=useLocation()
  const context=contextFor(location.pathname)
  const speaking=context==='speaking'
  const [open,setOpen]=useState(false)
  const [conversation,setConversation]=useState<Conversation|null>(null)
  const [draft,setDraft]=useState('')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [listening,setListening]=useState(false)
  const recognition=useRef<Recognition|null>(null)
  const bottom=useRef<HTMLDivElement|null>(null)
  useEffect(()=>{setError('');setDraft('');if(context==='mock')return;request<Conversation>(`/chat/${context}`).then(setConversation).catch(e=>setError(e.message))},[context])
  useEffect(()=>{bottom.current?.scrollIntoView({behavior:'smooth',block:'nearest'})},[conversation?.messages.length,open])
  useEffect(()=>()=>{recognition.current?.stop();window.speechSynthesis?.cancel()},[context])
  if(location.pathname==='/mock'||location.pathname==='/onboarding')return null
  const speak=(value:string)=>{if(!speaking||!('speechSynthesis' in window))return;window.speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(value.replace(/^DEMO assistant: /,''));utterance.lang='en-GB';utterance.rate=.9;window.speechSynthesis.speak(utterance)}
  const send=async(value=draft)=>{
    const message=value.trim();if(!message||busy)return
    setBusy(true);setError('');setDraft('')
    try{const next=await post<Conversation>(`/chat/${context}`,{message});setConversation(next);speak(next.messages[next.messages.length-1].text)}
    catch(e){setDraft(message);setError((e as Error).message)}
    finally{setBusy(false)}
  }
  const useMicrophone=()=>{
    if(listening){recognition.current?.stop();return}
    const BrowserRecognition=(window as any).SpeechRecognition||(window as any).webkitSpeechRecognition
    if(!BrowserRecognition){setError('Speech recognition is unavailable in this browser. Use Chrome or Edge, or record your practice response on the Speaking page.');return}
    try{const instance:Recognition=new BrowserRecognition();instance.lang='en-GB';instance.interimResults=false;instance.onresult=(event:any)=>{const transcript=event.results?.[0]?.[0]?.transcript?.trim();if(transcript){setDraft(transcript);void send(transcript)}};instance.onerror=(event:any)=>{setError(`Microphone recognition failed: ${event.error}`);setListening(false)};instance.onend=()=>setListening(false);recognition.current=instance;instance.start();setListening(true)}catch(e){setError((e as Error).message)}
  }
  return <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-3">
    {open&&<section className="flex h-[min(590px,75vh)] w-[min(390px,calc(100vw-40px))] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl" aria-label={`${conversation?.agent||'Agent'} conversation`}>
      <header className="flex items-center justify-between bg-navy px-4 py-3 text-white"><div className="flex items-center gap-2"><Bot size={19}/><div><div className="text-sm font-bold">{conversation?.agent||(speaking?'AI Tutor':'Learning Coordinator')}</div><div className="text-[11px] text-slate-300">{conversation?.mode==='DEMO'?'Deterministic demo':'Real AI'} · {context}</div></div></div><button onClick={()=>setOpen(false)} aria-label="Close agent chat"><X size={19}/></button></header>
      <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
        {!conversation?.messages.length&&<div className="rounded-xl bg-slate-100 p-3 text-sm text-slate-600">{speaking?'Say hello using the microphone or type to practise a conversation. This chat does not assess pronunciation.':`Ask me about ${context==='plan'?'your learning plan':context==='profile'?'your profile':context}. Formal results still pass quality review.`}</div>}
        {conversation?.messages.map((item,i)=><div key={i} className={`flex ${item.role==='learner'?'justify-end':'justify-start'}`}><div className={`max-w-[90%] rounded-2xl p-3 text-sm leading-relaxed ${item.role==='learner'?'bg-teal text-white':'bg-slate-100 text-slate-700'}`}>{item.text}{speaking&&item.role==='assistant'&&<button onClick={()=>speak(item.text)} aria-label="Read agent reply aloud" className="mt-2 flex items-center gap-1 text-xs font-bold text-teal"><Volume2 size={14}/> Listen</button>}</div></div>)}<div ref={bottom}/>
      </div>
      {error&&<p role="alert" className="mx-4 mb-2 text-xs text-red-700">{error}</p>}
      <form onSubmit={event=>{event.preventDefault();void send()}} className="flex items-center gap-2 border-t border-slate-100 p-3"><input aria-label="Message agent" className="input min-w-0 flex-1" value={draft} maxLength={2000} onChange={event=>setDraft(event.target.value)} placeholder={speaking?'Speak or type a reply…':'Ask the agent…'}/>{speaking&&<button type="button" onClick={useMicrophone} aria-label={listening?'Stop voice input':'Start voice input'} className={`rounded-xl p-2 ${listening?'bg-red-100 text-red-700':'bg-mint text-teal'}`} title="Browser speech recognition"><Mic size={19}/></button>}<button type="submit" disabled={busy||!draft.trim()} aria-label="Send agent message" className="rounded-xl bg-teal p-2 text-white disabled:opacity-40"><Send size={19}/></button></form>
    </section>}
    <button onClick={()=>setOpen(value=>!value)} aria-label={open?'Hide agent assistant':'Open agent assistant'} className="flex items-center gap-2 rounded-full bg-teal px-5 py-3 font-semibold text-white shadow-lg hover:bg-navy"><Bot size={21}/>{speaking?'Talk to AI Tutor':'Ask AI agent'}</button>
  </div>
}

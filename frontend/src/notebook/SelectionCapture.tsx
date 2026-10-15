import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { BookMarked, Check, Lock, MessageCircleQuestion, Quote, Volume2 } from 'lucide-react'
import { NotebookEntry, askTutor, notebookChanged, post, request } from '../api'
import { usePersona } from '../persona'
import { speak } from '../voice'
import { Notify } from '../ui'
import { isExamLocked, useIsExamLocked } from '../examLock'

type Popup = { text: string; context: string; x: number; top: number; above: boolean }
type Lookup = { word: string; phonetic?: string; translation?: string; meanings?: { pos: string; definition: string }[]; exam_tags?: string[]; lemma?: string; saved?: boolean }

function sentenceAround(selection: Selection, text: string) {
  const block = (selection.anchorNode?.parentElement?.closest('p, li, div, span, td') as HTMLElement | null)?.innerText || selection.anchorNode?.textContent || ''
  const sentences = block.replace(/\s+/g, ' ').match(/[^.!?。！？]+[.!?。！？]*/g) || [block]
  return (sentences.find(sentence => sentence.includes(text)) || block).trim().slice(0, 600)
}

function skillFromPath(path: string) {
  const match = path.match(/\/practice\/(\w+)/)
  return match ? match[1] : path.startsWith('/mock') ? 'mock' : ''
}

/* Select text anywhere. Outside tests: an instant dictionary card plus save / listen / ask.
   During a test: the word can only be saved; its meaning is revealed after the test. */
export default function SelectionCapture({ notify }: { notify: Notify }) {
  const location = useLocation()
  const { persona } = usePersona()
  const locked = useIsExamLocked()
  const [popup, setPopup] = useState<Popup | null>(null)
  const [lookup, setLookup] = useState<Lookup | null>(null)
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let startY = window.scrollY
    const onUp = (event: MouseEvent | TouchEvent) => {
      if (ref.current?.contains(event.target as Node)) return
      window.setTimeout(() => {
        const selection = window.getSelection()
        const text = selection?.toString().replace(/\s+/g, ' ').trim() || ''
        const target = event.target as HTMLElement
        if (!selection || !text || text.length > 400 || target.closest('input, textarea, select, button, [data-no-capture]') || !/[A-Za-z]/.test(text)) { setPopup(null); return }
        const rect = selection.getRangeAt(0).getBoundingClientRect()
        startY = window.scrollY
        const above = rect.top > 250
        setSaved(false)
        setLookup(null)
        setPopup({ text, context: sentenceAround(selection, text), x: Math.min(window.innerWidth - 340, Math.max(8, rect.left + rect.width / 2 - 165)), top: above ? Math.max(8, rect.top - 10) : Math.min(window.innerHeight - 80, rect.bottom + 10), above })
      }, 10)
    }
    const onDown = (event: MouseEvent) => { if (!ref.current?.contains(event.target as Node)) setPopup(null) }
    const onScroll = () => { if (Math.abs(window.scrollY - startY) > 60) setPopup(null) }
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setPopup(null) }
    document.addEventListener('mouseup', onUp)
    document.addEventListener('touchend', onUp)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    window.addEventListener('scroll', onScroll)
    return () => { document.removeEventListener('mouseup', onUp); document.removeEventListener('touchend', onUp); document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); window.removeEventListener('scroll', onScroll) }
  }, [])
  useEffect(() => setPopup(null), [location.pathname])

  const wordCount = popup ? popup.text.split(/\s+/).length : 0
  const isWord = !!popup && wordCount <= 5 && popup.text.length <= 60
  useEffect(() => {
    if (!popup || !isWord || isExamLocked()) return
    let cancelled = false
    request<Lookup>(`/dictionary?word=${encodeURIComponent(popup.text)}`).then(result => { if (!cancelled) { setLookup(result); setSaved(!!result.saved) } }).catch(() => { if (!cancelled) setLookup({ word: popup.text }) })
    return () => { cancelled = true }
  }, [popup?.text, popup?.x])

  if (!popup) return null
  const save = async (kind: 'word' | 'sentence') => {
    setBusy(true)
    try {
      const entry = await post<NotebookEntry & { hidden?: boolean }>('/notebook', { kind, text: popup.text, context: popup.context, skill: skillFromPath(location.pathname), exam: locked,
        source: (document.querySelector('main h1')?.textContent || location.pathname).trim().slice(0, 120), language: localStorage.getItem('native-language') || 'Chinese (Simplified)' })
      notify(kind === 'sentence' ? '✦ Saved to Sentence book' : entry.hidden ? `🔒 “${entry.text}” saved — its meaning appears in your Word book after the test` : `📒 “${entry.text}” ${entry.created ? 'saved to Word book' : 'is already saved (count +1)'}`)
      notebookChanged()
      if (kind === 'word') setSaved(true)
      if (locked || kind === 'sentence') { window.getSelection()?.removeAllRanges(); setPopup(null) }
    } catch (e) { notify((e as Error).message, 'error') } finally { setBusy(false) }
  }
  const tutorAvailable = !locked && Boolean(document.querySelector('[data-tutor-launcher]'))
  const style = { left: popup.x, top: popup.top, transform: popup.above ? 'translateY(-100%)' : undefined }

  if (locked) return <div ref={ref} data-no-capture role="toolbar" aria-label="Save selection" className="fixed z-[90]" style={style}>
    <div className="panel panel-sun !m-0 flex items-center gap-2 p-1.5 anim-pop">
      {isWord ? <button disabled={busy} onClick={() => save('word')} className="btn-primary !m-0 !px-2 !py-1 text-xs"><BookMarked size={14} /> Word book</button> : null}
      <span className="flex items-center gap-1 pr-1 font-pixel text-xs text-sun"><Lock size={12} /> {isWord ? 'Test mode · meaning hidden' : 'Test mode'}</span>
    </div>
  </div>

  return <div ref={ref} data-no-capture role="dialog" aria-label="Selection tools" className="fixed z-[90]" style={style}>
    <div className="panel panel-hot !m-0 w-[330px] max-w-[calc(100vw-16px)] p-3 anim-pop">
      {isWord && <div className="mb-2 min-h-[2.5rem]">
        <div className="flex items-baseline gap-2"><span className="font-pixel text-xl text-cyan">{popup.text.toLowerCase()}</span>{lookup?.phonetic && <span className="font-read text-xs text-fog">{lookup.phonetic}</span>}{lookup?.lemma && <span className="font-read text-xs text-mist">← {lookup.lemma}</span>}</div>
        {!lookup ? <div className="skeleton mt-2 h-3 w-3/4" />
          : lookup.translation || lookup.meanings?.length ? <div className="anim-fade">
            {lookup.translation && <p className="mt-1 font-read text-sm text-lime">{lookup.translation}</p>}
            {lookup.meanings?.[0] && <p className="mt-1 font-read text-xs text-mist"><i className="text-sun">{lookup.meanings[0].pos}</i> {lookup.meanings[0].definition}</p>}
            {lookup.exam_tags && lookup.exam_tags.length > 0 && <div className="mt-1 flex flex-wrap gap-1">{lookup.exam_tags.map(tag => <span key={tag} className="pill !text-[10px] text-cyan">{tag}</span>)}</div>}
          </div> : <p className="mt-1 font-read text-xs text-fog">Not in the offline dictionary — ask the tutor.</p>}
      </div>}
      <div className="flex flex-wrap items-center gap-1">
        {isWord && <button disabled={busy || saved} onClick={() => save('word')} className="btn-primary !m-0 !px-2 !py-1 text-xs">{saved ? <><Check size={14} /> In Word book</> : <><BookMarked size={14} /> Word book</>}</button>}
        {wordCount >= 4 && <button disabled={busy} onClick={() => save('sentence')} className="btn-cyan !m-0 !px-2 !py-1 text-xs"><Quote size={14} /> Sentence book</button>}
        <button onClick={() => speak(popup.text, persona, { force: true })} aria-label="Read selection aloud" className="btn-secondary !m-0 !px-2 !py-1"><Volume2 size={14} /></button>
        {tutorAvailable && <button onClick={() => { askTutor(isWord ? `I don't know the word "${popup.text}". In this sentence: "${popup.context}" — what does it mean?` : `Can you explain this sentence and its grammar? "${popup.text}"`); setPopup(null) }} className="btn-sun !m-0 !px-2 !py-1 text-xs"><MessageCircleQuestion size={14} /> Ask tutor</button>}
      </div>
    </div>
  </div>
}

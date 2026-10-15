import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { BookMarked, MessageCircleQuestion, Quote, Volume2 } from 'lucide-react'
import { NotebookEntry, askTutor, notebookChanged, post } from '../api'
import { usePersona } from '../persona'
import { speak } from '../voice'
import { Notify } from '../ui'

type Popup = { text: string; context: string; x: number; y: number }

function sentenceAround(selection: Selection, text: string) {
  const block = (selection.anchorNode?.parentElement?.closest('p, li, div, span, td') as HTMLElement | null)?.innerText || selection.anchorNode?.textContent || ''
  const sentences = block.replace(/\s+/g, ' ').match(/[^.!?。！？]+[.!?。！？]*/g) || [block]
  return (sentences.find(sentence => sentence.includes(text)) || block).trim().slice(0, 600)
}

function skillFromPath(path: string) {
  const match = path.match(/\/practice\/(\w+)/)
  return match ? match[1] : path.startsWith('/mock') ? 'mock' : ''
}

/* Select any text on any page → save it to the Word or Sentence book, hear it, or ask the tutor. */
export default function SelectionCapture({ notify }: { notify: Notify }) {
  const location = useLocation()
  const { persona } = usePersona()
  const [popup, setPopup] = useState<Popup | null>(null)
  const [busy, setBusy] = useState(false)
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const onUp = (event: MouseEvent | TouchEvent) => {
      if (ref.current?.contains(event.target as Node)) return
      window.setTimeout(() => {
        const selection = window.getSelection()
        const text = selection?.toString().replace(/\s+/g, ' ').trim() || ''
        const target = event.target as HTMLElement
        if (!selection || !text || text.length > 400 || target.closest('input, textarea, select, button, [data-no-capture]') || !/[A-Za-z]/.test(text)) { setPopup(null); return }
        const rect = selection.getRangeAt(0).getBoundingClientRect()
        startY = window.scrollY
        setPopup({ text, context: sentenceAround(selection, text), x: Math.min(window.innerWidth - 300, Math.max(8, rect.left + rect.width / 2 - 140)), y: Math.min(window.innerHeight - 64, Math.max(8, rect.top > 90 ? rect.top - 60 : rect.bottom + 10)) })
      }, 10)
    }
    const onDown = (event: MouseEvent) => { if (!ref.current?.contains(event.target as Node)) setPopup(null) }
    let startY = window.scrollY
    const onScroll = () => { if (Math.abs(window.scrollY - startY) > 60) { startY = window.scrollY; setPopup(null) } }
    document.addEventListener('mouseup', onUp)
    document.addEventListener('touchend', onUp)
    document.addEventListener('mousedown', onDown)
    window.addEventListener('scroll', onScroll)
    return () => { document.removeEventListener('mouseup', onUp); document.removeEventListener('touchend', onUp); document.removeEventListener('mousedown', onDown); window.removeEventListener('scroll', onScroll) }
  }, [])
  useEffect(() => setPopup(null), [location.pathname])

  if (!popup) return null
  const wordCount = popup.text.split(/\s+/).length
  const isWord = wordCount <= 5 && popup.text.length <= 60
  const save = async (kind: 'word' | 'sentence') => {
    setBusy(true)
    try {
      const entry = await post<NotebookEntry>('/notebook', { kind, text: popup.text, context: popup.context, skill: skillFromPath(location.pathname), source: (document.querySelector('main h1')?.textContent || location.pathname).trim().slice(0, 120), language: localStorage.getItem('native-language') || 'Chinese (Simplified)' })
      const meaning = entry.detail?.translation || entry.detail?.meanings?.[0]?.definition
      notify(kind === 'word' ? `📒 “${entry.text}” ${entry.created ? 'saved to Word book' : 'is already saved (count +1)'}${meaning ? ` — ${meaning}` : ''}` : '✦ Saved to Sentence book')
      notebookChanged()
      window.getSelection()?.removeAllRanges()
      setPopup(null)
    } catch (e) { notify((e as Error).message, 'error') } finally { setBusy(false) }
  }
  const tutorAvailable = Boolean(document.querySelector('[data-tutor-launcher]'))
  return <div ref={ref} data-no-capture role="toolbar" aria-label="Save selection" className="panel panel-hot fixed z-[90] !m-0 flex items-center gap-1 p-1.5 anim-rise" style={{ left: popup.x, top: popup.y }}>
    {isWord && <button disabled={busy} onClick={() => save('word')} className="btn-primary !m-0 !px-2 !py-1 text-xs"><BookMarked size={14} /> Word book</button>}
    {wordCount >= 4 && <button disabled={busy} onClick={() => save('sentence')} className="btn-cyan !m-0 !px-2 !py-1 text-xs"><Quote size={14} /> Sentence book</button>}
    <button onClick={() => speak(popup.text, persona, { force: true })} aria-label="Read selection aloud" className="btn-secondary !m-0 !px-2 !py-1"><Volume2 size={14} /></button>
    {tutorAvailable && <button onClick={() => { askTutor(isWord ? `I don't know the word "${popup.text}". In this sentence: "${popup.context}" — what does it mean?` : `Can you explain this sentence and its grammar? "${popup.text}"`); setPopup(null) }} className="btn-sun !m-0 !px-2 !py-1 text-xs"><MessageCircleQuestion size={14} /> Ask tutor</button>}
  </div>
}

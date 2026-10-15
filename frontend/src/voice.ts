/* Voice engine: cloud text-to-speech when the server offers it, otherwise the
   browser's Web Speech API, plus speech recognition helpers. */
import { health, token } from './api'

export type VoiceRole = 'witch' | 'boy' | 'narrator' | 'female' | 'male' | 'female2' | 'male2'

const listeners = new Set<(speaking: boolean) => void>()
export function onSpeakingChange(listener: (speaking: boolean) => void) { listeners.add(listener); return () => { listeners.delete(listener) } }
let speakingNow = false
function emit(value: boolean) { if (speakingNow !== value) { speakingNow = value; listeners.forEach(fn => fn(value)) } }
export const isSpeaking = () => speakingNow

export const prefs = {
  get rate() { return Number(localStorage.getItem('voice-rate') || '1') || 1 },
  set rate(value: number) { localStorage.setItem('voice-rate', String(value)) },
  get muted() { return localStorage.getItem('voice-muted') === '1' },
  set muted(value: boolean) { localStorage.setItem('voice-muted', value ? '1' : '0') },
  get handsFree() { return localStorage.getItem('voice-handsfree') !== '0' },
  set handsFree(value: boolean) { localStorage.setItem('voice-handsfree', value ? '1' : '0') },
}

/* ---------------- server voice ---------------- */
const audioCache = new Map<string, Promise<string>>()
let serverVoice: boolean | null = null
async function serverAvailable() {
  if (serverVoice !== null) return serverVoice
  try { serverVoice = (await health()).server_tts } catch { serverVoice = false }
  return serverVoice
}
function serverAudio(text: string, role: VoiceRole, rate: number): Promise<string> {
  const key = `${role}|${rate}|${text}`
  if (!audioCache.has(key)) {
    audioCache.set(key, fetch('/api/tts', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` }, body: JSON.stringify({ text, voice: role, speed: rate }) })
      .then(async response => { if (!response.ok) throw new Error('tts'); return URL.createObjectURL(await response.blob()) })
      .catch(error => { audioCache.delete(key); throw error }))
  }
  return audioCache.get(key)!
}
export function prefetch(text: string, role: VoiceRole, rate = prefs.rate) { void serverAvailable().then(ok => { if (ok) serverAudio(text, role, rate).catch(() => {}) }) }

/* ---------------- browser voice ---------------- */
const FEMALE = /(female|sonia|libby|maisie|hazel|susan|kate|serena|samantha|karen|moira|tessa|zira|aria|jenny|emma|ava|natasha|clara|michelle|ana|sara|fiona|victoria|allison|catherine)/i
const MALE = /(male|ryan|thomas|george|daniel|david|guy|mark|alex|fred|oliver|arthur|james|brian|william|christopher|eric|roger|aaron|tom|liam)/i
function voicesReady(): Promise<SpeechSynthesisVoice[]> {
  if (!('speechSynthesis' in window)) return Promise.resolve([])
  const now = speechSynthesis.getVoices()
  if (now.length) return Promise.resolve(now)
  return new Promise(resolve => {
    const done = () => resolve(speechSynthesis.getVoices())
    speechSynthesis.addEventListener('voiceschanged', done, { once: true })
    window.setTimeout(done, 1200)
  })
}
function rank(voice: SpeechSynthesisVoice) {
  return (/natural|neural|online/i.test(voice.name) ? 4 : 0) + (voice.lang === 'en-GB' ? 3 : voice.lang.startsWith('en-AU') || voice.lang.startsWith('en-US') ? 1 : 0) + (/google/i.test(voice.name) ? 1 : 0)
}
async function chooseVoice(role: VoiceRole) {
  const english = (await voicesReady()).filter(voice => voice.lang.toLowerCase().startsWith('en'))
  const sorted = [...english].sort((a, b) => rank(b) - rank(a))
  const female = sorted.filter(voice => FEMALE.test(voice.name) && !/\bmale\b/i.test(voice.name.replace(/female/i, '')))
  const male = sorted.filter(voice => MALE.test(voice.name) && !FEMALE.test(voice.name))
  const any = sorted
  const pick = (list: SpeechSynthesisVoice[], index: number) => list[index % Math.max(list.length, 1)] || any[index % Math.max(any.length, 1)]
  const table: Record<VoiceRole, [SpeechSynthesisVoice | undefined, number]> = {
    witch: [pick(female, 0), 1.12], female: [pick(female, 0), 1.0], female2: [pick(female, 1), female.length > 1 ? 1.0 : 1.25],
    boy: [pick(male, 0), 1.15], male: [pick(male, 0), 1.0], male2: [pick(male, 1), male.length > 1 ? 1.0 : .8], narrator: [pick(male.length > 2 ? male : female, 2), .95],
  }
  return table[role]
}
function chunks(text: string) {
  const parts = text.replace(/\s+/g, ' ').match(/[^.!?]+[.!?]*\s*/g) || [text]
  const out: string[] = []
  for (const part of parts) {
    if (out.length && (out[out.length - 1] + part).length < 180) out[out.length - 1] += part
    else out.push(part)
  }
  return out.map(item => item.trim()).filter(Boolean)
}

/* ---------------- public speak/stop ---------------- */
let stopCurrent: (() => void) | null = null
export function stopSpeaking() { stopCurrent?.(); stopCurrent = null; if ('speechSynthesis' in window) speechSynthesis.cancel(); emit(false) }

export async function speak(text: string, role: VoiceRole = 'witch', options: { rate?: number; force?: boolean } = {}): Promise<void> {
  const clean = text.replace(/[*_#`>]/g, '').trim()
  if (!clean || (prefs.muted && !options.force)) return
  stopSpeaking()
  const rate = options.rate ?? prefs.rate
  let cancelled = false
  emit(true)
  try {
    if (await serverAvailable()) {
      try {
        const url = await serverAudio(clean, role, rate)
        if (cancelled) return
        await new Promise<void>(resolve => {
          const audio = new Audio(url)
          stopCurrent = () => { cancelled = true; audio.pause(); resolve() }
          audio.onended = () => resolve()
          audio.onerror = () => resolve()
          audio.play().catch(() => resolve())
        })
        return
      } catch { /* fall back to the browser voice */ }
    }
    if (!('speechSynthesis' in window)) return
    const [voice, pitch] = await chooseVoice(role)
    for (const part of chunks(clean)) {
      if (cancelled) break
      await new Promise<void>(resolve => {
        const utterance = new SpeechSynthesisUtterance(part)
        if (voice) utterance.voice = voice
        utterance.lang = voice?.lang || 'en-GB'
        utterance.pitch = pitch
        utterance.rate = rate * (role === 'boy' ? 1.04 : 1)
        // Some engines never fire onend; resolve after a generous estimate of the speaking time.
        const guard = window.setTimeout(() => resolve(), 2500 + part.length * 95 / rate)
        utterance.onend = () => { window.clearTimeout(guard); resolve() }
        utterance.onerror = () => { window.clearTimeout(guard); resolve() }
        stopCurrent = () => { cancelled = true; window.clearTimeout(guard); resolve() }
        speechSynthesis.speak(utterance)
      })
    }
  } finally {
    if (!cancelled) emit(false)
  }
}

/* ---------------- recognition ---------------- */
type RecognitionLike = { lang: string; continuous: boolean; interimResults: boolean; maxAlternatives: number; onresult: ((event: any) => void) | null; onerror: ((event: any) => void) | null; onend: (() => void) | null; start: () => void; stop: () => void; abort: () => void }
const RecognitionCtor = () => (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
export const recognitionSupported = () => Boolean(RecognitionCtor())

export type Listener = { stop: () => void; abort: () => void }
/* Continuous recognition that reports final text and the live interim caption.
   It restarts itself if the browser ends the session early. */
export function listen(handlers: { onText: (finalText: string, interim: string) => void; onError?: (message: string) => void; onEnd?: () => void; lang?: string }): Listener {
  const Ctor = RecognitionCtor()
  if (!Ctor) { handlers.onError?.('Speech recognition is not available in this browser. Use Chrome or Edge, or type your answer.'); return { stop() {}, abort() {} } }
  let finalText = ''
  let active = true
  let instance: RecognitionLike | null = null
  const boot = () => {
    const rec: RecognitionLike = new Ctor()
    rec.lang = handlers.lang || 'en-GB'
    rec.continuous = true
    rec.interimResults = true
    rec.maxAlternatives = 1
    rec.onresult = (event: any) => {
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const piece = event.results[i][0].transcript
        if (event.results[i].isFinal) finalText = `${finalText} ${piece}`.trim()
        else interim += piece
      }
      handlers.onText(finalText, interim.trim())
    }
    rec.onerror = (event: any) => {
      if (event.error === 'no-speech' || event.error === 'aborted') return
      active = false
      handlers.onError?.(event.error === 'not-allowed' ? 'Microphone permission was blocked. Allow microphone access in the address bar.' : `Speech recognition error: ${event.error}`)
    }
    rec.onend = () => { if (active) { try { boot() } catch { active = false; handlers.onEnd?.() } } else handlers.onEnd?.() }
    instance = rec
    rec.start()
  }
  try { boot() } catch (error) { handlers.onError?.((error as Error).message) }
  return {
    stop() { active = false; try { instance?.stop() } catch { /* already stopped */ } },
    abort() { active = false; try { instance?.abort() } catch { /* already stopped */ } },
  }
}

/* Records the microphone (used for replay and for server transcription). */
export async function recordMicrophone(): Promise<{ stop: () => Promise<Blob> }> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const chunksList: BlobPart[] = []
  const type = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : ''
  const recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined)
  recorder.ondataavailable = event => { if (event.data.size) chunksList.push(event.data) }
  recorder.start(1000)
  return {
    stop: () => new Promise<Blob>(resolve => {
      recorder.onstop = () => { stream.getTracks().forEach(track => track.stop()); resolve(new Blob(chunksList, { type: 'audio/webm' })) }
      if (recorder.state !== 'inactive') recorder.stop(); else resolve(new Blob(chunksList, { type: 'audio/webm' }))
    }),
  }
}

export async function transcribeOnServer(blob: Blob): Promise<string> {
  const body = new FormData()
  body.append('file', blob, 'speech.webm')
  const response = await fetch('/api/stt', { method: 'POST', headers: { Authorization: `Bearer ${token()}` }, body })
  if (!response.ok) throw new Error('Server transcription is unavailable')
  return (await response.json()).text
}

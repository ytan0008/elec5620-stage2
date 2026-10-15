import { createContext, useContext, useEffect, useState } from 'react'
import { Persona, put } from './api'
import { onSpeakingChange, VoiceRole } from './voice'
import type { AvatarMood } from './pixel/Avatar'

type PersonaState = { persona: Persona; setPersona: (persona: Persona) => void; aiSpeaking: boolean }
const PersonaContext = createContext<PersonaState>({ persona: 'witch', setPersona: () => {}, aiSpeaking: false })

export function PersonaProvider({ initial, onChange, children }: { initial: Persona; onChange?: (persona: Persona) => void; children: React.ReactNode }) {
  const [persona, setLocal] = useState<Persona>(initial)
  const [aiSpeaking, setAiSpeaking] = useState(false)
  useEffect(() => setLocal(initial), [initial])
  useEffect(() => onSpeakingChange(setAiSpeaking), [])
  const setPersona = (next: Persona) => {
    setLocal(next)
    onChange?.(next)
    put('/me/avatar', { avatar: next }).catch(() => { /* preference stays local if offline */ })
  }
  return <PersonaContext.Provider value={{ persona, setPersona, aiSpeaking }}>{children}</PersonaContext.Provider>
}

export const usePersona = () => useContext(PersonaContext)
export const personaVoice = (persona: Persona): VoiceRole => persona
export function moodFor(aiSpeaking: boolean, listening: boolean, thinking: boolean): AvatarMood {
  return aiSpeaking ? 'talking' : listening ? 'listening' : thinking ? 'thinking' : 'idle'
}

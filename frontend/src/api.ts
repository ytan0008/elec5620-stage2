export type Persona = 'witch' | 'boy'
export type User = { id: number; email: string; name: string; role: 'learner' | 'instructor'; avatar?: Persona; profile_complete?: boolean }
export type Profile = { exam: 'IELTS' | 'TOEFL'; proficiency: string; target_score: number; exam_date: string; weekly_hours: number; priority_skills: string[] }
export type Result = { id: number; kind: string; state: string; source_mode: string; issues: string[]; payload?: Record<string, any>; confidence?: Record<string, number>; message?: string; created_at: string }
export type AdaptationOutcome = { outcome: string; plan_id: number | null; message: string | null }
export type AdaptationNotice = { outcome: string; message: string; trigger: string | null; created_at: string | null }
export type Plan = { id: number; version: number; kind: string; status: string; content?: Record<string, any>; created_at: string }
export type Health = { status: string; mode: 'LOCAL' | 'REAL'; model: string; server_tts: boolean; server_stt: boolean }

export type ScriptLine = { voice: string; speaker: string; text: string }
export type Option = { key: string; text: string }
export type Question = { n: number; prompt?: string; options?: Option[]; clip?: ScriptLine[]; prefix?: string }
export type Group = { title: string; type: 'completion' | 'mcq' | 'matching' | 'tfng' | 'ynng' | 'cwords'; instructions: string; heading?: string; options?: Option[]; text?: string; questions: Question[] }
export type Section = { id: string; kind: 'listening' | 'reading'; exam: string; part: number; title: string; topic?: string; context?: string; script?: ScriptLine[]; passage?: { label: string; text: string }[]; minutes?: number; groups: Group[] }
export type ObjectiveTest = { kind: 'listening' | 'reading'; exam: string; title: string; sections: Section[]; minutes?: number | null }
export type Chart = { type: 'bar' | 'line' | 'pie'; title: string; unit: string; categories: string[]; series: { name: string; values: number[] }[] }
export type WritingTask = { id: string; task: string; title: string; prompt: string; chart?: Chart | null; min_words: number; minutes: number }
export type SpeakingTest = Record<string, any>
export type PracticePrompt = { title: string; text: string; mode: string; task_type?: string; duration_seconds: number; test?: any; task?: string; min_words?: number; chart?: Chart | null; content_id?: string }
export type Practice = { id: number; skill: string; prompt: PracticePrompt }
export type Mock = { id: number; exam: string; status: string; length: string; legacy: boolean; created_at: string; duration_seconds: number; sections: Record<string, any>; answers: Record<string, string>; result: Result | null; adaptation?: AdaptationOutcome | null
  ended?: { reason: string; at: string; completed: string[]; missing: string[] } | null; report_id?: number | null
  timing?: MockTiming | null }
export type MockTiming = { current: 'listening' | 'reading' | 'writing' | null; current_deadline: string | null; closed: string[]; written_started: boolean; written_done: boolean
  speaking_done: boolean; day_deadline: string; day_over: boolean; minutes: Record<string, number> }
export type Event = { id: number; workflow: string; agent: string; phase: string; detail: Record<string, any>; mode: string; duration_ms: number; created_at: string }
export type SpeakingView = { id: number; exam: string; status: string; practice_id: number | null; mock_id: number | null; persona: Persona; log: { role: string; text: string; stage?: string; part?: string; seconds?: number; repeat_accuracy?: number; repeat_target?: string; follow_up?: boolean }[]; ui: { part: string; stage: string; progress?: string; cue_card?: { topic: string; cue: string; bullets: string[]; closing: string }; timer?: { kind: string; seconds: number } }; test_title?: string; reply?: string; done?: boolean; result?: Result; metrics?: Record<string, number>; saved_to_mock?: boolean }

export const token = () => localStorage.getItem('certifyai_token')

export async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const auth = token()
  const headers: Record<string, string> = { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...(auth ? { Authorization: `Bearer ${auth}` } : {}) }
  const response = await fetch(`/api${path}`, { ...options, headers: { ...headers, ...(options.headers as Record<string, string> | undefined) } })
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      detail = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map((d: any) => d.msg).join('; ') : JSON.stringify(body.detail)
    } catch { /* keep generic message */ }
    throw new Error(detail)
  }
  return response.json()
}
export function post<T = any>(path: string, data?: unknown): Promise<T> { return request<T>(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) }) }
export function put<T = any>(path: string, data: unknown): Promise<T> { return request<T>(path, { method: 'PUT', body: JSON.stringify(data) }) }

let healthCache: Promise<Health> | null = null
export function health(refresh = false): Promise<Health> {
  if (!healthCache || refresh) healthCache = request<Health>('/health').catch(error => { healthCache = null; throw error })
  return healthCache
}

export type NotebookKind = 'mistake' | 'word' | 'grammar' | 'sentence'
export type NotebookEntry = { id: number; kind: NotebookKind; text: string; category: string; skill: string; source: string; detail: Record<string, any>; count: number; mastered: boolean; review_level: number; due: boolean; next_review: string; created_at: string; updated_at: string; created?: boolean; hidden?: boolean }
export type NotebookStats = { counts: Record<NotebookKind, { total: number; active: number; mastered: number }>; mistakes_by_type: { name: string; count: number }[]; mistakes_by_skill: { name: string; count: number }[]; grammar_issues: { name: string; count: number }[]; due_words: number; due_mistakes: number }
export type Memory = { id: number; kind: string; text: string; source: string; updated_at: string }
export type ChatEvent = { type: 'word' | 'memory' | 'quiz'; word?: string; text?: string; created?: boolean; remembered?: boolean; id?: number }
export type ChatMessage = { role: string; text: string; quiz?: string; coach?: boolean }

/* Lets any component ask the floating tutor a question (e.g. from a text selection). */
export function askTutor(message: string) { window.dispatchEvent(new CustomEvent('ask-tutor', { detail: message })) }
export function notebookChanged() { window.dispatchEvent(new Event('notebook-changed')) }

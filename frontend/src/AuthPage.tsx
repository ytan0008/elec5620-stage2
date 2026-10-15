import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, GraduationCap } from 'lucide-react'
import { User, post } from './api'

type Mode = 'register' | 'login' | 'forgot' | 'reset'
type Props = {
  onAuth: (user: User, token: string) => void
  notify: (message: string, kind?: 'success' | 'error') => void
}

const skills = ['writing', 'speaking', 'reading', 'listening']
const nice = (value: string) => value.charAt(0).toUpperCase() + value.slice(1)

export default function AuthPage({ onAuth, notify }: Props) {
  const navigate = useNavigate()
  const initialToken = new URLSearchParams(window.location.search).get('token') || ''
  const [mode, setMode] = useState<Mode>(initialToken ? 'reset' : 'register')
  const [token, setToken] = useState(initialToken)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [demoPath, setDemoPath] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [form, setForm] = useState({
    name: '', email: '', password: '', exam: 'IELTS', proficiency: 'intermediate',
    target_score: 7, exam_date: '2026-12-15', weekly_hours: 8,
    priority_skills: ['writing'] as string[],
  })
  const update = (key: string, value: unknown) => setForm(previous => ({ ...previous, [key]: value }))
  const switchMode = (next: Mode) => { setMode(next); setMessage(''); setDemoPath('') }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (mode === 'reset' && form.password !== confirmPassword) {
      notify('Passwords do not match', 'error')
      return
    }
    setBusy(true)
    setMessage('')
    try {
      if (mode === 'forgot') {
        const response = await post<{message: string; demo_reset_path?: string; demo_notice?: string}>('/auth/password-reset/request', { email: form.email })
        setMessage(response.demo_notice || response.message)
        setDemoPath(response.demo_reset_path || '')
      } else if (mode === 'reset') {
        const response = await post<{message: string}>('/auth/password-reset/confirm', { token, password: form.password })
        notify(response.message)
        setForm(previous => ({ ...previous, password: '' }))
        setConfirmPassword('')
        setToken('')
        switchMode('login')
        navigate('/')
      } else {
        const body = mode === 'login' ? { email: form.email, password: form.password } : form
        const response = await post<{token: string; user: User}>(`/auth/${mode}`, body)
        onAuth(response.user, response.token)
      }
    } catch (error) {
      notify((error as Error).message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return <div className="min-h-screen bg-navy text-white">
    <div className="mx-auto grid min-h-screen max-w-7xl lg:grid-cols-2">
      <div className="flex flex-col justify-between p-8 md:p-14">
        <div className="flex items-center gap-3 font-display text-xl font-bold">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-mint text-teal"><GraduationCap /></div>CertifyAI
        </div>
        <div className="py-16">
          <span className="rounded-full bg-white/10 px-3 py-1 text-sm text-mint">ELEC5620 · Stage 2 prototype</span>
          <h1 className="font-display mt-6 max-w-xl text-5xl font-bold leading-tight md:text-6xl">Your English goal deserves a <span className="text-mint">clear path.</span></h1>
          <p className="mt-6 max-w-lg text-lg text-slate-300">Personalised IELTS and TOEFL practice with transparent quality checks and human oversight.</p>
          <div className="mt-12 grid max-w-md grid-cols-3 gap-4 text-sm">
            <div><strong className="text-2xl text-mint">4</strong><p className="text-slate-400">AI roles</p></div>
            <div><strong className="text-2xl text-mint">4</strong><p className="text-slate-400">Core skills</p></div>
            <div><strong className="text-2xl text-mint">100%</strong><p className="text-slate-400">Quality gated</p></div>
          </div>
        </div>
        <p className="text-sm text-slate-400">Practice estimates are not official examination results.</p>
      </div>
      <div className="flex items-center justify-center bg-cream p-5 text-ink md:p-10">
        <form onSubmit={submit} className="card w-full max-w-lg p-7 md:p-9">
          {(mode === 'register' || mode === 'login') && <div className="mb-7 flex rounded-xl bg-slate-100 p-1">
            <button type="button" onClick={() => switchMode('register')} className={`w-1/2 rounded-lg py-2 text-sm font-bold ${mode === 'register' ? 'bg-white shadow-sm' : 'text-slate-500'}`}>Create account</button>
            <button type="button" onClick={() => switchMode('login')} className={`w-1/2 rounded-lg py-2 text-sm font-bold ${mode === 'login' ? 'bg-white shadow-sm' : 'text-slate-500'}`}>Sign in</button>
          </div>}
          <h2 className="heading text-2xl">{{ register: 'Start your learning journey', login: 'Welcome back', forgot: 'Recover your account', reset: 'Set a new password' }[mode]}</h2>
          <p className="mb-6 mt-2 text-sm text-slate-500">{{ register: 'Tell us your goal so your coordinator can build a plan.', login: 'Pick up where you left off.', forgot: 'Enter the email you used to register.', reset: 'This link can be used once and expires after 30 minutes.' }[mode]}</p>
          <div className="space-y-4">
            {mode === 'register' && <label className="block"><span className="label">Full name</span><input className="input" required value={form.name} onChange={event => update('name', event.target.value)} /></label>}
            {mode !== 'reset' && <label className="block"><span className="label">Email</span><input className="input" required type="email" value={form.email} onChange={event => update('email', event.target.value)} /></label>}
            {mode !== 'forgot' && <label className="block"><span className="label">{mode === 'reset' ? 'New password' : 'Password'}</span><input className="input" required minLength={8} maxLength={128} type="password" autoComplete={mode === 'register' || mode === 'reset' ? 'new-password' : 'current-password'} value={form.password} onChange={event => update('password', event.target.value)} /></label>}
            {mode === 'reset' && <label className="block"><span className="label">Confirm new password</span><input className="input" required minLength={8} type="password" autoComplete="new-password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} /></label>}
            {mode === 'register' && <>
              <div className="grid grid-cols-2 gap-3">
                <label><span className="label">Target exam</span><select className="input" value={form.exam} onChange={event => setForm(previous => ({ ...previous, exam: event.target.value, target_score: event.target.value === 'IELTS' ? 7 : 4.5 }))}><option>IELTS</option><option>TOEFL</option></select></label>
                <label><span className="label">Current level</span><select className="input" value={form.proficiency} onChange={event => update('proficiency', event.target.value)}><option>beginner</option><option>intermediate</option><option>advanced</option></select></label>
                <label><span className="label">Target score</span><input className="input" type="number" min={form.exam === 'IELTS' ? 0 : 1} max={form.exam === 'IELTS' ? 9 : 6} step="0.5" value={form.target_score} onChange={event => update('target_score', Number(event.target.value))} /></label>
                <label><span className="label">Exam date</span><input className="input" type="date" required value={form.exam_date} onChange={event => update('exam_date', event.target.value)} /></label>
              </div>
              <label className="block"><span className="label">Study hours per week</span><input className="input" type="number" min="1" max="40" value={form.weekly_hours} onChange={event => update('weekly_hours', Number(event.target.value))} /></label>
              <div><span className="label">Priority skills</span><div className="flex flex-wrap gap-2">{skills.map(skill => <button type="button" key={skill} onClick={() => update('priority_skills', form.priority_skills.includes(skill) ? form.priority_skills.filter(item => item !== skill) : [...form.priority_skills, skill])} className={`pill border ${form.priority_skills.includes(skill) ? 'border-teal bg-mint text-teal' : 'border-slate-200 text-slate-500'}`}>{nice(skill)}</button>)}</div></div>
            </>}
          </div>
          {message && <p role="status" className="mt-5 rounded-xl bg-mint p-3 text-sm text-teal">{message}</p>}
          {demoPath && <Link to={demoPath} onClick={() => { setToken(new URL(demoPath, window.location.origin).searchParams.get('token') || ''); switchMode('reset') }} className="mt-3 block break-all text-sm font-semibold text-teal underline">Open demo reset link</Link>}
          <button disabled={busy} className="btn-primary mt-7 w-full">{busy ? 'Working…' : { register: 'Create account', login: 'Sign in', forgot: 'Send reset link', reset: 'Change password' }[mode]}<ArrowRight size={18} /></button>
          {mode === 'login' && <button type="button" onClick={() => switchMode('forgot')} className="mt-4 w-full text-center text-sm font-semibold text-teal underline">Forgot password?</button>}
          {(mode === 'forgot' || mode === 'reset') && <button type="button" onClick={() => { switchMode('login'); navigate('/') }} className="mt-4 w-full text-center text-sm font-semibold text-teal underline">Back to sign in</button>}
          <p className="mt-4 text-center text-xs text-slate-400">Demo mode works without an AI API key.</p>
        </form>
      </div>
    </div>
  </div>
}

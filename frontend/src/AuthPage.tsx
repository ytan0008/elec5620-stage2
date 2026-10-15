import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Wand2 } from 'lucide-react'
import { User, post } from './api'
import { PixelAvatar } from './pixel/Avatar'

type Mode = 'register' | 'login' | 'forgot' | 'reset'
type Props = { onAuth: (user: User, token: string) => void; notify: (message: string, kind?: 'success' | 'error') => void }

export default function AuthPage({ onAuth, notify }: Props) {
  const navigate = useNavigate()
  const initialToken = new URLSearchParams(window.location.search).get('token') || ''
  const [mode, setMode] = useState<Mode>(initialToken ? 'reset' : 'login')
  const [token, setToken] = useState(initialToken)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [resetPath, setResetPath] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const update = (key: string, value: unknown) => setForm(previous => ({ ...previous, [key]: value }))
  const switchMode = (next: Mode) => { setMode(next); setMessage(''); setResetPath('') }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (mode === 'reset' && form.password !== confirmPassword) { notify('Passwords do not match', 'error'); return }
    setBusy(true); setMessage('')
    try {
      if (mode === 'forgot') {
        const response = await post<{ message: string; reset_path?: string; notice?: string }>('/auth/password-reset/request', { email: form.email })
        setMessage(response.notice || response.message)
        setResetPath(response.reset_path || '')
      } else if (mode === 'reset') {
        const response = await post<{ message: string }>('/auth/password-reset/confirm', { token, password: form.password })
        notify(response.message)
        setForm(previous => ({ ...previous, password: '' })); setConfirmPassword(''); setToken('')
        switchMode('login'); navigate('/')
      } else {
        const body = mode === 'login' ? { email: form.email, password: form.password } : form
        const response = await post<{ token: string; user: User }>(`/auth/${mode}`, body)
        onAuth(response.user, response.token)
      }
    } catch (error) { notify((error as Error).message, 'error') } finally { setBusy(false) }
  }

  return <div className="min-h-screen">
    <div className="mx-auto grid min-h-screen max-w-7xl items-center gap-10 p-6 lg:grid-cols-[1.1fr_.9fr] lg:p-12">
      <div className="space-y-8">
        <div className="flex items-center gap-3"><span className="grid h-11 w-11 place-items-center bg-magenta text-night" style={{ boxShadow: '0 0 0 3px #140c2e, 4px 4px 0 3px #3ef0ff' }}><Wand2 /></span><span className="font-arcade text-sm">Certify<span className="text-cyan">AI</span> <span className="text-magenta">· Pixel Academy</span></span></div>
        <h1 className="heading title-glow anim-glitch text-5xl leading-tight md:text-7xl">Level up your<br /><span className="text-cyan">IELTS</span> &amp; <span className="text-sun">TOEFL</span>.</h1>
        <p className="max-w-xl font-read text-lg text-mist">Real exam-format listening with multiple voices, authentic reading tasks, rubric feedback on writing — and a live spoken interview with your pixel examiner.</p>
        <div className="flex items-end gap-6">
          <div className="text-center"><PixelAvatar persona="witch" mood="happy" size={130} /><p className="font-pixel text-magenta">Luna</p></div>
          <div className="text-center"><PixelAvatar persona="boy" mood="idle" size={110} /><p className="font-pixel text-ember">Kai</p></div>
          <div className="tile mb-10 max-w-xs font-read text-sm">“Pick one of us as your tutor. We'll talk, listen and guide you to your target band.”</div>
        </div>
      </div>
      <form onSubmit={submit} className="panel panel-hot w-full p-7 md:p-9">
        {(mode === 'register' || mode === 'login') && <div className="mb-7 grid grid-cols-2 gap-1">
          <button type="button" onClick={() => switchMode('login')} className={mode === 'login' ? 'btn-primary' : 'btn-secondary'}>Sign in</button>
          <button type="button" onClick={() => switchMode('register')} className={mode === 'register' ? 'btn-primary' : 'btn-secondary'}>Sign up</button>
        </div>}
        <h2 className="heading text-3xl">{{ register: 'Start your journey', login: 'Welcome back', forgot: 'Recover your account', reset: 'Set a new password' }[mode]}</h2>
        <p className="mb-6 mt-2 font-read text-sm text-mist">{{ register: 'Create an account; your AI coordinator then builds your profile with you.', login: 'Pick up where you left off.', forgot: 'Enter the email you registered with.', reset: 'This link can be used once and expires after 30 minutes.' }[mode]}</p>
        <div className="space-y-4">
          {mode === 'register' && <label className="block"><span className="label">Full name</span><input className="input" required value={form.name} onChange={event => update('name', event.target.value)} /></label>}
          {mode !== 'reset' && <label className="block"><span className="label">Email</span><input className="input" required type="email" value={form.email} onChange={event => update('email', event.target.value)} /></label>}
          {mode !== 'forgot' && <label className="block"><span className="label">{mode === 'reset' ? 'New password' : 'Password'}</span><input className="input" required minLength={8} maxLength={128} type="password" autoComplete={mode === 'register' || mode === 'reset' ? 'new-password' : 'current-password'} value={form.password} onChange={event => update('password', event.target.value)} /></label>}
          {mode === 'reset' && <label className="block"><span className="label">Confirm new password</span><input className="input" required minLength={8} type="password" autoComplete="new-password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} /></label>}
        </div>
        {message && <p role="status" className="tile mt-5 font-read text-sm text-cyan">{message}</p>}
        {resetPath && <Link to={resetPath} onClick={() => { setToken(new URL(resetPath, window.location.origin).searchParams.get('token') || ''); switchMode('reset') }} className="btn-ghost mt-3">Open reset link</Link>}
        <button disabled={busy} className="btn-primary mt-7 w-full">{busy ? 'Working…' : { register: 'Create account', login: 'Sign in', forgot: 'Send reset link', reset: 'Change password' }[mode]}<ArrowRight size={17} /></button>
        {mode === 'login' && <button type="button" onClick={() => switchMode('forgot')} className="btn-ghost mt-4 w-full justify-center">Forgot password?</button>}
        {(mode === 'forgot' || mode === 'reset') && <button type="button" onClick={() => { switchMode('login'); navigate('/') }} className="btn-ghost mt-4 w-full justify-center">Back to sign in</button>}
        <p className="mt-4 text-center font-read text-xs text-fog">Practice scores are estimates, not official results.</p>
      </form>
    </div>
  </div>
}

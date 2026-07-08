'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api, setTokens, setUserProfile, getAccessToken } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Zap } from 'lucide-react'

type Mode = 'login' | 'register'

export default function LoginPage() {
  const router = useRouter()
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [tenantName, setTenantName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const [brokerLoading, setBrokerLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)

  useEffect(() => {
    if (getAccessToken()) router.replace('/')
  }, [router])

  async function handleGoogleLogin() {
    setError(null)
    setGoogleLoading(true)
    try {
      const { login_url, state } = await api.getGoogleLoginUrl()
      // Cross-checked against the state Google echoes back (login-CSRF guard).
      sessionStorage.setItem('google_login_state', state)
      window.location.href = login_url
    } catch (err: unknown) {
      const raw = err instanceof Error ? err.message : 'Google sign-in unavailable'
      try {
        setError(JSON.parse(raw).detail ?? raw)
      } catch {
        setError(raw)
      }
      setGoogleLoading(false)
    }
  }

  async function handleUpstoxLogin() {
    setError(null)
    setBrokerLoading(true)
    try {
      const { login_url, state } = await api.getUpstoxLoginUrl()
      // The callback page cross-checks this against the state Upstox echoes
      // back, so a login-CSRF redirect from another browser session fails.
      sessionStorage.setItem('upstox_login_state', state)
      window.location.href = login_url
    } catch (err: unknown) {
      const raw = err instanceof Error ? err.message : 'Upstox sign-in unavailable'
      try {
        const parsed = JSON.parse(raw)
        setError(parsed.detail ?? raw)
      } catch {
        setError(raw)
      }
      setBrokerLoading(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const tokens = mode === 'login'
        ? await api.login(email, password)
        : await api.register({ email, password, display_name: displayName, tenant_name: tenantName })
      setTokens(tokens.access_token, tokens.refresh_token)
      setUserProfile({
        display_name: tokens.display_name,
        tenant_name: tokens.tenant_name,
        plan: tokens.plan,
        email: tokens.email,
      })
      router.replace('/')
    } catch (err: unknown) {
      const raw = err instanceof Error ? err.message : 'Something went wrong'
      try {
        const parsed = JSON.parse(raw)
        setError(parsed.detail ?? raw)
      } catch {
        setError(raw)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative z-10">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex flex-col items-center mb-10">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-600 flex items-center justify-center mb-4 shadow-[0_0_40px_rgba(139,92,246,0.35)]">
            <Zap className="w-7 h-7 text-white fill-white/20" />
          </div>
          <h1 className="text-2xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-zinc-900 to-zinc-500 dark:from-white dark:to-zinc-400 tracking-tight">
            AlphaSwarm
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
            {mode === 'login' ? 'Sign in to your trading terminal' : 'Create your trading workspace'}
          </p>
        </div>

        {/* Card */}
        <div className="glass-card rounded-3xl p-8 border border-white/10 shadow-[0_8px_40px_rgba(0,0,0,0.12)]">
          {/* Mode toggle */}
          <div className="flex rounded-xl overflow-hidden border border-zinc-200 dark:border-zinc-700 mb-7 p-1 bg-zinc-100/50 dark:bg-zinc-800/50">
            {(['login', 'register'] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => { setMode(m); setError(null) }}
                className={`flex-1 py-2 text-sm font-semibold rounded-lg transition-all duration-200 ${
                  mode === m
                    ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 shadow-sm'
                    : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
                }`}
              >
                {m === 'login' ? 'Sign In' : 'Create Account'}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'register' && (
              <>
                <Field label="Workspace name" id="tenant">
                  <input
                    id="tenant"
                    type="text"
                    required
                    placeholder="Acme Trading Co."
                    value={tenantName}
                    onChange={(e) => setTenantName(e.target.value)}
                    className={inputCls}
                  />
                </Field>
                <Field label="Display name" id="displayName">
                  <input
                    id="displayName"
                    type="text"
                    required
                    placeholder="Your name"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    className={inputCls}
                  />
                </Field>
              </>
            )}

            <Field label="Email" id="email">
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                placeholder="trader@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={inputCls}
              />
            </Field>

            <Field label="Password" id="password">
              <input
                id="password"
                type="password"
                required
                minLength={mode === 'register' ? 8 : 1}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                placeholder={mode === 'register' ? 'Min. 8 characters' : '••••••••'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputCls}
              />
            </Field>

            {mode === 'login' && (
              <div className="text-right -mt-1">
                <a href="/forgot-password" className="text-xs font-semibold text-violet-500 hover:text-violet-400">
                  Forgot password?
                </a>
              </div>
            )}

            {error && (
              <div className="rounded-xl px-4 py-3 bg-rose-500/10 border border-rose-500/20 text-sm text-rose-500 dark:text-rose-400">
                {error}
              </div>
            )}

            <Button type="submit" loading={loading} className="w-full mt-2 h-12 text-sm shadow-[0_0_20px_rgba(139,92,246,0.25)] hover:shadow-[0_0_30px_rgba(139,92,246,0.4)]">
              {mode === 'login' ? 'Sign In' : 'Create Account'}
            </Button>
          </form>

          {/* ── Broker-identity sign-in ─────────────────────────────── */}
          <div className="flex items-center gap-3 my-5">
            <div className="flex-1 h-px bg-zinc-200 dark:bg-zinc-700" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">or</span>
            <div className="flex-1 h-px bg-zinc-200 dark:bg-zinc-700" />
          </div>

          <button
            type="button"
            onClick={handleGoogleLogin}
            disabled={googleLoading}
            className="w-full h-12 mb-3 flex items-center justify-center gap-2.5 rounded-xl text-sm font-semibold
              bg-white dark:bg-zinc-800/80 border border-zinc-200 dark:border-zinc-700
              text-zinc-800 dark:text-zinc-100
              hover:border-violet-400/60 hover:shadow-[0_0_16px_rgba(139,92,246,0.15)]
              disabled:opacity-60 transition-all duration-150"
          >
            {googleLoading ? (
              <span className="w-4 h-4 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
            ) : (
              <svg className="w-5 h-5" viewBox="0 0 24 24" aria-hidden="true">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z" />
              </svg>
            )}
            Continue with Google
          </button>

          <button
            type="button"
            onClick={handleUpstoxLogin}
            disabled={brokerLoading}
            className="w-full h-12 flex items-center justify-center gap-2.5 rounded-xl text-sm font-semibold
              bg-white dark:bg-zinc-800/80 border border-zinc-200 dark:border-zinc-700
              text-zinc-800 dark:text-zinc-100
              hover:border-violet-400/60 hover:shadow-[0_0_16px_rgba(139,92,246,0.15)]
              disabled:opacity-60 transition-all duration-150"
          >
            {brokerLoading ? (
              <span className="w-4 h-4 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
            ) : (
              <span className="w-5 h-5 rounded-md bg-[#5A2FD1] flex items-center justify-center text-[10px] font-black text-white">
                UP
              </span>
            )}
            Continue with Upstox
          </button>
          <p className="text-center text-[11px] text-zinc-400 dark:text-zinc-500 mt-3">
            Signs you in <em>and</em> connects your brokerage — no API keys to copy.
          </p>

          <p className="text-center text-xs text-zinc-500 dark:text-zinc-400 mt-5">
            Prefer a one-time code?{' '}
            <a href="/login/otp" className="font-semibold text-violet-500 hover:text-violet-400">
              Sign in with email or phone
            </a>
          </p>
        </div>

        <p className="text-center text-xs text-zinc-400 dark:text-zinc-500 mt-6">
          Founding Member plan · First 500 users free · No credit card required
        </p>
      </div>
    </div>
  )
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
        {label}
      </label>
      {children}
    </div>
  )
}

const inputCls = [
  'w-full h-11 px-4 rounded-xl text-sm',
  'bg-white dark:bg-zinc-800/80',
  'border border-zinc-200 dark:border-zinc-700',
  'text-zinc-900 dark:text-zinc-100',
  'placeholder:text-zinc-400 dark:placeholder:text-zinc-500',
  'focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500/50',
  'transition-all duration-150',
].join(' ')

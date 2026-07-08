'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Mail, KeyRound, ArrowLeft } from 'lucide-react'
import { api, setTokens, setUserProfile } from '@/lib/api'
import { Button } from '@/components/ui/Button'

/**
 * Passwordless sign-in with a one-time code. One field accepts either an email
 * OR a phone number — the backend classifies it and delivers the code by email
 * or SMS. New users are created on first verified code, so this doubles as
 * registration. This is the "sign in as email OR phone" path.
 */
export default function OtpLoginPage() {
  const router = useRouter()
  const [step, setStep] = useState<'request' | 'verify'>('request')
  const [identifier, setIdentifier] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  function parseError(err: unknown, fallback: string): string {
    const raw = err instanceof Error ? err.message : fallback
    try {
      return (JSON.parse(raw).detail as string) ?? raw
    } catch {
      return raw
    }
  }

  async function handleRequest(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await api.requestOtp(identifier.trim())
      setNotice(res.detail)
      setStep('verify')
    } catch (err) {
      setError(parseError(err, 'Could not send a code.'))
    } finally {
      setLoading(false)
    }
  }

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const tokens = await api.verifyOtp(identifier.trim(), code.trim())
      setTokens(tokens.access_token, tokens.refresh_token)
      setUserProfile({
        display_name: tokens.display_name,
        tenant_name: tokens.tenant_name,
        plan: tokens.plan,
        email: tokens.email,
      })
      router.replace('/')
    } catch (err) {
      setError(parseError(err, 'Verification failed.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative z-10">
      <div className="w-full max-w-md">
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-600 flex items-center justify-center mb-3">
            {step === 'request' ? (
              <Mail className="w-6 h-6 text-white" />
            ) : (
              <KeyRound className="w-6 h-6 text-white" />
            )}
          </div>
          <h1 className="text-xl font-extrabold text-zinc-900 dark:text-zinc-100">
            {step === 'request' ? 'Sign in with a code' : 'Enter your code'}
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1 text-center">
            {step === 'request'
              ? 'Use your email or mobile number — no password needed.'
              : `We sent a 6-digit code to ${identifier}.`}
          </p>
        </div>

        <div className="glass-card rounded-3xl p-8 border border-white/10 shadow-[0_8px_40px_rgba(0,0,0,0.12)]">
          {step === 'request' ? (
            <form onSubmit={handleRequest} className="space-y-4">
              <input
                type="text"
                required
                autoFocus
                autoComplete="username"
                placeholder="Email or mobile number"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                className={inputCls}
              />
              {error && <ErrorBox>{error}</ErrorBox>}
              <Button type="submit" loading={loading} className="w-full h-12 text-sm">
                Send code
              </Button>
            </form>
          ) : (
            <form onSubmit={handleVerify} className="space-y-4">
              {notice && (
                <div className="rounded-xl px-4 py-3 bg-emerald-500/10 border border-emerald-500/20 text-sm text-emerald-600 dark:text-emerald-400">
                  {notice}
                </div>
              )}
              <input
                type="text"
                required
                autoFocus
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={6}
                autoComplete="one-time-code"
                placeholder="123456"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                className={`${inputCls} tracking-[0.5em] text-center text-lg font-semibold`}
              />
              {error && <ErrorBox>{error}</ErrorBox>}
              <Button type="submit" loading={loading} className="w-full h-12 text-sm">
                Verify & sign in
              </Button>
              <button
                type="button"
                onClick={() => {
                  setStep('request')
                  setCode('')
                  setError(null)
                  setNotice(null)
                }}
                className="w-full flex items-center justify-center gap-1.5 text-xs font-semibold text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Use a different email or number
              </button>
            </form>
          )}
        </div>

        <p className="text-center text-xs text-zinc-400 dark:text-zinc-500 mt-6">
          <Link href="/login" className="font-semibold text-violet-500 hover:text-violet-400">
            Back to password sign-in
          </Link>
        </p>
      </div>
    </div>
  )
}

function ErrorBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl px-4 py-3 bg-rose-500/10 border border-rose-500/20 text-sm text-rose-500 dark:text-rose-400">
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

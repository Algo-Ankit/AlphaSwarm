'use client'
import { useState } from 'react'
import Link from 'next/link'
import { KeyRound, MailCheck } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/Button'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await api.forgotPassword(email)
      setSent(true)
    } catch (err: unknown) {
      const raw = err instanceof Error ? err.message : 'Something went wrong'
      try {
        setError((JSON.parse(raw).detail as string) ?? raw)
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
        <div className="glass-card rounded-3xl p-8 border border-white/10 shadow-[0_8px_40px_rgba(0,0,0,0.12)]">
          {sent ? (
            <div className="text-center">
              <MailCheck className="w-12 h-12 mx-auto mb-4 text-emerald-500" />
              <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-2">Check your inbox</h1>
              <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-6">
                If <span className="font-semibold">{email}</span> is registered, a reset link is on its
                way. It expires in 30 minutes.
              </p>
              <Link href="/login" className="text-sm font-semibold text-violet-500 hover:text-violet-400">
                Back to sign in
              </Link>
            </div>
          ) : (
            <>
              <div className="text-center mb-7">
                <KeyRound className="w-10 h-10 mx-auto mb-3 text-violet-500" />
                <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100">Forgot your password?</h1>
                <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
                  Enter your email and we&apos;ll send you a reset link.
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <input
                  type="email"
                  required
                  autoComplete="email"
                  placeholder="trader@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className={inputCls}
                />

                {error && (
                  <div className="rounded-xl px-4 py-3 bg-rose-500/10 border border-rose-500/20 text-sm text-rose-500 dark:text-rose-400">
                    {error}
                  </div>
                )}

                <Button type="submit" loading={loading} className="w-full h-12 text-sm">
                  Send reset link
                </Button>
              </form>

              <p className="text-center text-xs text-zinc-400 dark:text-zinc-500 mt-5">
                Remembered it?{' '}
                <Link href="/login" className="font-semibold text-violet-500 hover:text-violet-400">
                  Sign in
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
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

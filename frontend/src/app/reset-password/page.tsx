'use client'
import { Suspense, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { CheckCircle2, ShieldCheck } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/Button'

// useSearchParams() requires a Suspense boundary in Next 14 static builds.
export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPassword />
    </Suspense>
  )
}

function ResetPassword() {
  const params = useSearchParams()
  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setLoading(true)
    try {
      await api.resetPassword(token, password)
      setDone(true)
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
          {done ? (
            <div className="text-center">
              <CheckCircle2 className="w-12 h-12 mx-auto mb-4 text-emerald-500" />
              <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-2">Password updated</h1>
              <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-6">
                All your sessions were signed out. Sign in with your new password.
              </p>
              <Link
                href="/login"
                className="inline-block px-5 py-2.5 rounded-xl bg-violet-600 text-white text-sm font-semibold hover:bg-violet-700 transition-colors"
              >
                Go to sign in
              </Link>
            </div>
          ) : !token ? (
            <div className="text-center">
              <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-2">Missing reset token</h1>
              <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-6">
                Open this page from the link in your reset email.
              </p>
              <Link href="/forgot-password" className="text-sm font-semibold text-violet-500 hover:text-violet-400">
                Request a new link
              </Link>
            </div>
          ) : (
            <>
              <div className="text-center mb-7">
                <ShieldCheck className="w-10 h-10 mx-auto mb-3 text-violet-500" />
                <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100">Choose a new password</h1>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <input
                  type="password"
                  required
                  minLength={8}
                  autoComplete="new-password"
                  placeholder="New password (min. 8 characters)"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={inputCls}
                />
                <input
                  type="password"
                  required
                  minLength={8}
                  autoComplete="new-password"
                  placeholder="Confirm new password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className={inputCls}
                />

                {error && (
                  <div className="rounded-xl px-4 py-3 bg-rose-500/10 border border-rose-500/20 text-sm text-rose-500 dark:text-rose-400">
                    {error}
                  </div>
                )}

                <Button type="submit" loading={loading} className="w-full h-12 text-sm">
                  Reset password
                </Button>
              </form>
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

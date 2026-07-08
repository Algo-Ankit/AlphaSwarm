'use client'
import { Suspense, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'

// useSearchParams() requires a Suspense boundary in Next 14 static builds.
export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmail />
    </Suspense>
  )
}

function VerifyEmail() {
  const params = useSearchParams()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const calledRef = useRef(false)

  useEffect(() => {
    if (calledRef.current) return
    calledRef.current = true

    async function verify() {
      const token = params.get('token')
      if (!token) {
        setStatus('error')
        setMessage('Missing verification token — open this page from the link in your email.')
        return
      }
      try {
        const res = await api.verifyEmail(token)
        setStatus('success')
        setMessage(res.detail)
      } catch (err: unknown) {
        const raw = err instanceof Error ? err.message : 'Verification failed.'
        try {
          setMessage((JSON.parse(raw).detail as string) ?? raw)
        } catch {
          setMessage(raw)
        }
        setStatus('error')
      }
    }

    verify()
  }, [params])

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-950">
      <div className="max-w-sm w-full mx-4 text-center">
        {status === 'loading' && (
          <>
            <Loader2 className="w-12 h-12 mx-auto mb-4 text-violet-500 animate-spin" />
            <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-2">Verifying your email…</h1>
          </>
        )}

        {status === 'success' && (
          <>
            <CheckCircle2 className="w-12 h-12 mx-auto mb-4 text-emerald-500" />
            <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-2">Email verified!</h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-6">{message}</p>
            <Link
              href="/"
              className="inline-block px-5 py-2.5 rounded-xl bg-violet-600 text-white text-sm font-semibold hover:bg-violet-700 transition-colors"
            >
              Go to dashboard
            </Link>
          </>
        )}

        {status === 'error' && (
          <>
            <XCircle className="w-12 h-12 mx-auto mb-4 text-rose-500" />
            <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-2">Verification failed</h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-6">{message}</p>
            <Link href="/login" className="text-sm font-semibold text-violet-500 hover:text-violet-400">
              Back to sign in
            </Link>
          </>
        )}
      </div>
    </div>
  )
}

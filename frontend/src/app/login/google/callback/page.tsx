'use client'
import { Suspense, useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { api, setTokens, setUserProfile } from '@/lib/api'

/**
 * "Continue with Google" landing page. Google redirects here with
 * ?code=…&state=…. The state must match what THIS browser stored when it
 * started the flow (login-CSRF guard); the backend additionally verifies the
 * state's signature and expiry, then exchanges the code, finds-or-creates the
 * account, and returns platform tokens. Unlike the broker flows, Google
 * connects no brokerage — it is pure identity.
 */
// useSearchParams() requires a Suspense boundary in Next 14 static builds.
export default function GoogleLoginCallbackPage() {
  return (
    <Suspense fallback={null}>
      <GoogleLoginCallback />
    </Suspense>
  )
}

function GoogleLoginCallback() {
  const router = useRouter()
  const params = useSearchParams()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const calledRef = useRef(false)

  useEffect(() => {
    if (calledRef.current) return
    calledRef.current = true

    async function exchange() {
      const code = params.get('code')
      const state = params.get('state')
      const stored = sessionStorage.getItem('google_login_state')
      sessionStorage.removeItem('google_login_state')

      if (!code || !state) {
        setStatus('error')
        setMessage(
          params.get('error_description') || params.get('error') || 'Google did not return an authorization code.'
        )
        return
      }
      if (!stored || stored !== state) {
        setStatus('error')
        setMessage('Sign-in state mismatch — please restart from the login page.')
        return
      }

      try {
        const tokens = await api.googleLoginCallback(code, state)
        setTokens(tokens.access_token, tokens.refresh_token)
        setUserProfile({
          display_name: tokens.display_name,
          tenant_name: tokens.tenant_name,
          plan: tokens.plan,
          email: tokens.email,
        })
        setStatus('success')
        setMessage(`Welcome, ${tokens.display_name}.`)
        setTimeout(() => router.replace('/'), 1200)
      } catch (err: unknown) {
        const raw = err instanceof Error ? err.message : 'Google sign-in failed.'
        setStatus('error')
        try {
          setMessage((JSON.parse(raw).detail as string) ?? raw)
        } catch {
          setMessage(raw)
        }
      }
    }

    exchange()
  }, [params, router])

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-950">
      <div className="max-w-sm w-full mx-4 text-center">
        {status === 'loading' && (
          <>
            <Loader2 className="w-12 h-12 mx-auto mb-4 text-violet-500 animate-spin" />
            <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-2">Signing you in with Google…</h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">Verifying your identity</p>
          </>
        )}

        {status === 'success' && (
          <>
            <CheckCircle2 className="w-12 h-12 mx-auto mb-4 text-emerald-500" />
            <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-2">Signed in!</h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">{message}</p>
            <p className="text-xs text-zinc-400 mt-2">Taking you to your dashboard…</p>
          </>
        )}

        {status === 'error' && (
          <>
            <XCircle className="w-12 h-12 mx-auto mb-4 text-rose-500" />
            <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-2">Sign-in failed</h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-6">{message}</p>
            <button
              onClick={() => router.replace('/login')}
              className="px-5 py-2.5 rounded-xl bg-violet-600 text-white text-sm font-semibold hover:bg-violet-700 transition-colors"
            >
              Back to Login
            </button>
          </>
        )}
      </div>
    </div>
  )
}

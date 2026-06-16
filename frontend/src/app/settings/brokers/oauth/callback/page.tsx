'use client'
import { useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'

/**
 * OAuth callback landing page.
 *
 * Brokers redirect here after the user authorises AlphaSwarm:
 *  - Upstox:  ?code=…&state=…
 *  - Zerodha: ?request_token=…&action=login&status=success
 *
 * We read the URL params, call the backend to exchange the code/token, then
 * redirect back to /settings/brokers.
 */
export default function OAuthCallbackPage() {
  const router       = useRouter()
  const params       = useSearchParams()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const calledRef = useRef(false)

  useEffect(() => {
    if (calledRef.current) return
    calledRef.current = true

    async function exchange() {
      const code         = params.get('code')
      const state        = params.get('state')
      const requestToken = params.get('request_token')
      const action       = params.get('action')
      const zpStatus     = params.get('status')

      // ── Zerodha callback ──────────────────────────────────────
      if (requestToken || (action === 'login' && zpStatus === 'success')) {
        if (!requestToken) {
          setStatus('error')
          setMessage('Zerodha did not return a request_token.')
          return
        }
        try {
          await api.exchangeBrokerOAuthCode({ broker: 'zerodha', request_token: requestToken })
          setStatus('success')
          setMessage('Zerodha connected successfully!')
          setTimeout(() => router.replace('/settings/brokers'), 2000)
        } catch (err: unknown) {
          setStatus('error')
          setMessage(err instanceof Error ? err.message : 'Zerodha token exchange failed.')
        }
        return
      }

      // ── Upstox callback ───────────────────────────────────────
      if (code) {
        try {
          await api.exchangeBrokerOAuthCode({ broker: 'upstox', code, state: state ?? undefined })
          setStatus('success')
          setMessage('Upstox connected successfully!')
          setTimeout(() => router.replace('/settings/brokers'), 2000)
        } catch (err: unknown) {
          setStatus('error')
          setMessage(err instanceof Error ? err.message : 'Upstox token exchange failed.')
        }
        return
      }

      // ── Error returned by broker ──────────────────────────────
      const errDesc = params.get('error_description') || params.get('error') || 'Unknown error from broker.'
      setStatus('error')
      setMessage(errDesc)
    }

    exchange()
  }, [params, router])

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-950">
      <div className="max-w-sm w-full mx-4 text-center">
        {status === 'loading' && (
          <>
            <Loader2 className="w-12 h-12 mx-auto mb-4 text-violet-500 animate-spin" />
            <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-2">Connecting your broker…</h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">Exchanging authorisation code</p>
          </>
        )}

        {status === 'success' && (
          <>
            <CheckCircle2 className="w-12 h-12 mx-auto mb-4 text-emerald-500" />
            <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-2">Connected!</h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">{message}</p>
            <p className="text-xs text-zinc-400 mt-2">Redirecting you back…</p>
          </>
        )}

        {status === 'error' && (
          <>
            <XCircle className="w-12 h-12 mx-auto mb-4 text-rose-500" />
            <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-2">Connection failed</h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-6">{message}</p>
            <button
              onClick={() => router.replace('/settings/brokers')}
              className="px-5 py-2.5 rounded-xl bg-violet-600 text-white text-sm font-semibold hover:bg-violet-700 transition-colors"
            >
              Back to Broker Settings
            </button>
          </>
        )}
      </div>
    </div>
  )
}

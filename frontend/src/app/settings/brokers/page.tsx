'use client'
import { useState, useEffect } from 'react'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { api } from '@/lib/api'
import type { BrokerConnection } from '@/lib/types'
import {
  Link2,
  Trash2,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Eye,
  EyeOff,
  ChevronDown,
  ChevronUp,
  ExternalLink,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const BROKER_META: Record<string, { name: string; logo: string; color: string; exchange: string }> = {
  alpaca:   { name: 'Alpaca',      logo: 'A', color: 'from-yellow-400 to-orange-500',  exchange: 'US stocks & crypto' },
  upstox:   { name: 'Upstox',      logo: 'U', color: 'from-purple-500 to-violet-600',  exchange: 'NSE / BSE' },
  zerodha:  { name: 'Zerodha',     logo: 'Z', color: 'from-sky-500 to-blue-600',        exchange: 'NSE / BSE intraday' },
  angelone: { name: 'AngelOne',    logo: 'AO', color: 'from-rose-500 to-pink-600',      exchange: 'NSE / BSE' },
}

function TokenStatusBadge({ status }: { status: string }) {
  if (status === 'connected') return <Badge variant="success" dot>Token valid</Badge>
  if (status === 'expired')   return <Badge variant="warning" dot>Token expired — re-login</Badge>
  return null
}

function ConnectionCard({ conn, onDelete }: { conn: BrokerConnection; onDelete: (id: string) => void }) {
  const [testing,    setTesting]    = useState(false)
  const [deleting,   setDeleting]   = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [relogging,  setRelogging]  = useState(false)

  const meta = BROKER_META[conn.broker] ?? { name: conn.broker, logo: conn.broker[0]?.toUpperCase() ?? '?', color: 'from-zinc-400 to-zinc-600', exchange: '' }

  async function handleTest() {
    setTesting(true); setTestResult(null)
    try {
      const r = await api.testBroker(conn.id)
      setTestResult({ ok: r.ok, message: r.message })
    } catch { setTestResult({ ok: false, message: 'Request failed' }) }
    finally { setTesting(false) }
  }

  async function handleDelete() {
    setDeleting(true); setDeleteError(null)
    try { await api.deleteBroker(conn.id); onDelete(conn.id) }
    catch { setDeleteError('Remove failed — please try again.'); setDeleting(false) }
  }

  async function handleReLogin() {
    if (!['upstox', 'zerodha'].includes(conn.broker)) return
    setRelogging(true)
    try {
      const { login_url } = await api.getBrokerOAuthLoginUrl(conn.broker)
      window.location.href = login_url
    } catch (err) {
      setTestResult({ ok: false, message: err instanceof Error ? err.message : 'Failed to get login URL' })
      setRelogging(false)
    }
  }

  return (
    <GlassCard padding="none" className="overflow-hidden">
      <div className="flex items-center gap-4 px-6 py-5">
        <div className={cn('flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-sm bg-gradient-to-br', meta.color)}>
          {meta.logo}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="text-[15px] font-semibold text-zinc-900 dark:text-zinc-100">{meta.name}</span>
            <span className={cn(
              'text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-widest',
              conn.is_paper
                ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300'
                : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300',
            )}>
              {conn.is_paper ? 'Paper' : 'Live'}
            </span>
            {conn.oauth_connected && <TokenStatusBadge status={conn.token_status} />}
          </div>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-0.5 font-mono">{conn.key_preview}</p>
          {conn.token_expires_at && (
            <p className="text-xs text-zinc-400 mt-0.5">
              Token expires: {new Date(conn.token_expires_at).toLocaleString()}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {conn.oauth_connected && conn.token_status === 'expired' && ['upstox', 'zerodha'].includes(conn.broker) && (
            <button onClick={handleReLogin} disabled={relogging}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-500/10 transition-colors disabled:opacity-40">
              <ExternalLink className={cn('w-3.5 h-3.5', relogging && 'animate-spin')} />
              Re-Login
            </button>
          )}
          {conn.broker === 'alpaca' && (
            <button onClick={handleTest} disabled={testing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors disabled:opacity-40">
              <RefreshCw className={cn('w-3.5 h-3.5', testing && 'animate-spin')} />
              Test
            </button>
          )}
          <button onClick={handleDelete} disabled={deleting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-500/10 transition-colors disabled:opacity-40">
            <Trash2 className="w-3.5 h-3.5" />
            Remove
          </button>
        </div>
      </div>

      {deleteError && (
        <div className="flex items-center gap-2.5 px-6 py-3 border-t border-rose-100 dark:border-rose-500/20 bg-rose-50/60 dark:bg-rose-500/10 text-sm font-medium text-rose-600 dark:text-rose-400">
          <XCircle className="w-4 h-4 flex-shrink-0" />{deleteError}
        </div>
      )}
      {testResult && (
        <div className={cn(
          'flex items-center gap-2.5 px-6 py-3 border-t text-sm font-medium',
          testResult.ok
            ? 'border-emerald-100 dark:border-emerald-500/20 bg-emerald-50/60 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
            : 'border-rose-100 dark:border-rose-500/20 bg-rose-50/60 dark:bg-rose-500/10 text-rose-600 dark:text-rose-400',
        )}>
          {testResult.ok ? <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> : <XCircle className="w-4 h-4 flex-shrink-0" />}
          {testResult.message}
        </div>
      )}
    </GlassCard>
  )
}

// ── Alpaca (API-key) form ──────────────────────────────────────────────────────
function AddAlpacaForm({ onAdded }: { onAdded: (conn: BrokerConnection) => void }) {
  const [open, setOpen]           = useState(false)
  const [apiKey, setApiKey]       = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [isPaper, setIsPaper]     = useState(true)
  const [showSecret, setShowSecret] = useState(false)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); setLoading(true); setError(null)
    try {
      const conn = await api.connectBroker({ broker: 'alpaca', api_key: apiKey.trim(), api_secret: apiSecret.trim(), is_paper: isPaper })
      onAdded(conn); setApiKey(''); setApiSecret(''); setOpen(false)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Connection failed'
      try { const p = JSON.parse(msg); setError(typeof p === 'string' ? p : p.detail ?? msg) }
      catch { setError(msg) }
    } finally { setLoading(false) }
  }

  return (
    <GlassCard padding="none" className="overflow-hidden">
      <button type="button" onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-6 py-5 hover:bg-zinc-50/50 dark:hover:bg-white/[0.03] transition-colors">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-gradient-to-br from-yellow-400 to-orange-500 text-white font-bold text-sm flex-shrink-0">A</div>
          <div className="text-left">
            <p className="text-[15px] font-semibold text-zinc-900 dark:text-zinc-100">Connect Alpaca</p>
            <p className="text-xs text-zinc-500 mt-0.5">US stocks &amp; crypto — paper or live trading</p>
          </div>
        </div>
        {open ? <ChevronUp className="w-5 h-5 text-zinc-400" /> : <ChevronDown className="w-5 h-5 text-zinc-400" />}
      </button>

      <div className={cn('grid transition-all duration-300 ease-in-out', open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0')}>
        <div className="overflow-hidden">
          <form onSubmit={handleSubmit} className="px-6 pb-6 pt-2 border-t border-black/[0.05] dark:border-white/[0.05] space-y-5">
            <div className="flex gap-3 pt-2">
              {[true, false].map((paper) => (
                <button key={String(paper)} type="button"
                  onClick={() => {
                    if (!paper && isPaper && !window.confirm('Enable LIVE trading? This will use real capital.')) return
                    setIsPaper(paper)
                  }}
                  className={cn(
                    'flex-1 py-2.5 rounded-xl text-sm font-semibold border transition-all duration-150',
                    isPaper === paper
                      ? paper ? 'bg-indigo-500 border-indigo-500 text-white' : 'bg-emerald-500 border-emerald-500 text-white'
                      : 'border-zinc-200 dark:border-zinc-700 text-zinc-500 dark:text-zinc-400',
                  )}>
                  {paper ? 'Paper Trading' : 'Live Trading'}
                </button>
              ))}
            </div>
            {!isPaper && (
              <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20">
                <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                <p className="text-xs font-medium text-amber-700 dark:text-amber-300">Live trading uses real capital. Ensure risk limits are configured correctly.</p>
              </div>
            )}
            <div>
              <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">API Key ID</label>
              <input type="text" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                placeholder="PKXXXXXXXXXXXXXXXXXXXXXXXX" required autoComplete="off" spellCheck={false}
                className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl px-4 py-3 text-sm font-mono text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-violet-500/30 transition-shadow" />
            </div>
            <div>
              <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Secret Key</label>
              <div className="relative">
                <input type={showSecret ? 'text' : 'password'} value={apiSecret} onChange={(e) => setApiSecret(e.target.value)}
                  placeholder="••••••••••••••••••••••••••••••••" required autoComplete="new-password" spellCheck={false}
                  className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl px-4 py-3 pr-11 text-sm font-mono text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-violet-500/30 transition-shadow" />
                <button type="button" onClick={() => setShowSecret(!showSecret)} tabIndex={-1}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300">
                  {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            {error && (
              <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20">
                <XCircle className="w-4 h-4 text-rose-500 mt-0.5 flex-shrink-0" />
                <p className="text-sm font-medium text-rose-600 dark:text-rose-400">{error}</p>
              </div>
            )}
            <Button type="submit" loading={loading} disabled={!apiKey.trim() || !apiSecret.trim()} className="w-full">
              {!loading && <Link2 className="w-4 h-4 mr-2" />}
              {loading ? 'Validating & Connecting…' : 'Connect Alpaca'}
            </Button>
          </form>
        </div>
      </div>
    </GlassCard>
  )
}

// ── Zerodha (API-key + OAuth redirect) ────────────────────────────────────────
function AddZerodhaForm({ onAdded, existing }: { onAdded: (c: BrokerConnection) => void; existing: boolean }) {
  const [open, setOpen]           = useState(false)
  const [apiKey, setApiKey]       = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [savingKeys, setSavingKeys] = useState(false)
  const [redirecting, setRedirecting] = useState(false)
  const [error, setError]         = useState<string | null>(null)

  async function handleSaveKeys(e: React.FormEvent) {
    e.preventDefault(); setSavingKeys(true); setError(null)
    try {
      await api.connectBroker({ broker: 'zerodha', api_key: apiKey.trim(), api_secret: apiSecret.trim(), is_paper: false })
      setApiKey(''); setApiSecret('')
      // after saving keys, trigger the OAuth redirect
      await handleOAuthLogin()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save keys')
    } finally { setSavingKeys(false) }
  }

  async function handleOAuthLogin() {
    setRedirecting(true)
    try {
      const { login_url } = await api.getBrokerOAuthLoginUrl('zerodha')
      window.location.href = login_url
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to get Zerodha login URL')
      setRedirecting(false)
    }
  }

  return (
    <GlassCard padding="none" className="overflow-hidden">
      <button type="button" onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-6 py-5 hover:bg-zinc-50/50 dark:hover:bg-white/[0.03] transition-colors">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-gradient-to-br from-sky-500 to-blue-600 text-white font-bold text-sm flex-shrink-0">Z</div>
          <div className="text-left">
            <p className="text-[15px] font-semibold text-zinc-900 dark:text-zinc-100">Zerodha Kite</p>
            <p className="text-xs text-zinc-500 mt-0.5">Indian intraday — NSE/BSE via OAuth</p>
          </div>
        </div>
        {open ? <ChevronUp className="w-5 h-5 text-zinc-400" /> : <ChevronDown className="w-5 h-5 text-zinc-400" />}
      </button>

      <div className={cn('grid transition-all duration-300 ease-in-out', open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0')}>
        <div className="overflow-hidden">
          <div className="px-6 pb-6 pt-2 border-t border-black/[0.05] dark:border-white/[0.05]">
            {existing ? (
              <div className="pt-4 space-y-3">
                <p className="text-xs text-zinc-500 dark:text-zinc-400">Zerodha access tokens expire daily. Click below to re-authorise.</p>
                <Button onClick={handleOAuthLogin} loading={redirecting} className="w-full">
                  {!redirecting && <ExternalLink className="w-4 h-4 mr-2" />}
                  {redirecting ? 'Opening Zerodha…' : 'Login with Zerodha'}
                </Button>
              </div>
            ) : (
              <form onSubmit={handleSaveKeys} className="space-y-4 pt-4">
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  Enter your Zerodha Kite API key &amp; secret, then you'll be redirected to authorise.
                </p>
                <div>
                  <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">API Key</label>
                  <input type="text" value={apiKey} onChange={(e) => setApiKey(e.target.value)} required autoComplete="off"
                    className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl px-4 py-3 text-sm font-mono text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-violet-500/30" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">API Secret</label>
                  <input type="password" value={apiSecret} onChange={(e) => setApiSecret(e.target.value)} required autoComplete="new-password"
                    className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl px-4 py-3 text-sm font-mono text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-violet-500/30" />
                </div>
                {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
                <Button type="submit" loading={savingKeys} disabled={!apiKey.trim() || !apiSecret.trim()} className="w-full">
                  {!savingKeys && <ExternalLink className="w-4 h-4 mr-2" />}
                  {savingKeys ? 'Saving & Redirecting…' : 'Save & Login with Zerodha'}
                </Button>
              </form>
            )}
          </div>
        </div>
      </div>
    </GlassCard>
  )
}

// ── Upstox (platform OAuth) ───────────────────────────────────────────────────
function UpstoxOAuthButton({ onAdded }: { onAdded?: (c: BrokerConnection) => void }) {
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  async function handleLogin() {
    setLoading(true); setError(null)
    try {
      const { login_url } = await api.getBrokerOAuthLoginUrl('upstox')
      window.location.href = login_url
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed'
      // Likely means UPSTOX_CLIENT_ID not configured
      setError(msg.includes('not configured') ? 'Upstox OAuth is not yet configured by the platform admin.' : msg)
      setLoading(false)
    }
  }

  return (
    <GlassCard padding="none" className="overflow-hidden">
      <div className="flex items-center gap-3 px-6 py-5">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-gradient-to-br from-purple-500 to-violet-600 text-white font-bold text-sm flex-shrink-0">U</div>
        <div className="flex-1">
          <p className="text-[15px] font-semibold text-zinc-900 dark:text-zinc-100">Upstox</p>
          <p className="text-xs text-zinc-500 mt-0.5">Indian markets (NSE/BSE) via OAuth</p>
        </div>
        <Button size="sm" variant="secondary" onClick={handleLogin} loading={loading}>
          {!loading && <ExternalLink className="w-3.5 h-3.5 mr-1.5" />}
          {loading ? 'Opening…' : 'Login with Upstox'}
        </Button>
      </div>
      {error && (
        <div className="flex items-center gap-2 px-6 py-3 border-t border-amber-100 dark:border-amber-500/20 bg-amber-50/60 dark:bg-amber-500/10 text-xs font-medium text-amber-700 dark:text-amber-300">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />{error}
        </div>
      )}
    </GlassCard>
  )
}

// ── AngelOne (credential login) ───────────────────────────────────────────────
function AngelOneForm({ onAdded }: { onAdded: (c: BrokerConnection) => void }) {
  const [open, setOpen]       = useState(false)
  const [clientId, setClientId] = useState('')
  const [password, setPassword] = useState('')
  const [totp, setTotp]       = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); setLoading(true); setError(null)
    try {
      const conn = await api.angeloneLogin({ client_id: clientId.trim(), password, totp: totp.trim() })
      onAdded(conn); setClientId(''); setPassword(''); setTotp(''); setOpen(false)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally { setLoading(false) }
  }

  return (
    <GlassCard padding="none" className="overflow-hidden">
      <button type="button" onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-6 py-5 hover:bg-zinc-50/50 dark:hover:bg-white/[0.03] transition-colors">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-gradient-to-br from-rose-500 to-pink-600 text-white font-bold text-[10px] flex-shrink-0">AO</div>
          <div className="text-left">
            <p className="text-[15px] font-semibold text-zinc-900 dark:text-zinc-100">AngelOne</p>
            <p className="text-xs text-zinc-500 mt-0.5">NSE/BSE via TOTP login</p>
          </div>
        </div>
        {open ? <ChevronUp className="w-5 h-5 text-zinc-400" /> : <ChevronDown className="w-5 h-5 text-zinc-400" />}
      </button>

      <div className={cn('grid transition-all duration-300 ease-in-out', open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0')}>
        <div className="overflow-hidden">
          <form onSubmit={handleSubmit} className="px-6 pb-6 pt-2 border-t border-black/[0.05] dark:border-white/[0.05] space-y-4">
            <div className="flex items-start gap-2.5 px-4 py-3 mt-2 rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20">
              <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
              <p className="text-xs font-medium text-amber-700 dark:text-amber-300">Enter your Client Code, MPIN, and current TOTP. AlphaSwarm does not store your password in plaintext.</p>
            </div>
            {[
              { label: 'Client Code', value: clientId,  set: setClientId,  type: 'text',     ph: 'e.g. A123456' },
              { label: 'MPIN',        value: password,  set: setPassword,  type: 'password', ph: '4–6 digit MPIN' },
              { label: 'TOTP',        value: totp,      set: setTotp,      type: 'text',     ph: '6-digit authenticator code' },
            ].map((f) => (
              <div key={f.label}>
                <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">{f.label}</label>
                <input type={f.type} value={f.value} onChange={(e) => f.set(e.target.value)} placeholder={f.ph} required
                  autoComplete="off" spellCheck={false} maxLength={f.label === 'TOTP' ? 8 : 32}
                  className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl px-4 py-3 text-sm font-mono text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-violet-500/30" />
              </div>
            ))}
            {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
            <Button type="submit" loading={loading} disabled={!clientId.trim() || !password || !totp.trim()} className="w-full">
              {!loading && <Link2 className="w-4 h-4 mr-2" />}
              {loading ? 'Logging in…' : 'Login to AngelOne'}
            </Button>
          </form>
        </div>
      </div>
    </GlassCard>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function BrokerSettingsPage() {
  const [connections, setConnections] = useState<BrokerConnection[]>([])
  const [loading, setLoading]         = useState(true)

  useEffect(() => {
    api.listBrokers().then(setConnections).catch(() => {}).finally(() => setLoading(false))
  }, [])

  function handleAdded(conn: BrokerConnection) {
    setConnections((prev) => [...prev.filter((c) => c.broker !== conn.broker), conn])
  }
  function handleDeleted(id: string) {
    setConnections((prev) => prev.filter((c) => c.id !== id))
  }

  const alpacaConnected   = connections.some((c) => c.broker === 'alpaca')
  const zerodhaConnected  = connections.some((c) => c.broker === 'zerodha')

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto animate-slide-up relative z-10 pb-20">
        <div className="mb-10">
          <h1 className="text-3xl font-extrabold text-zinc-900 dark:text-zinc-100 tracking-tight">Broker Connections</h1>
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            Connect your own broker account. AlphaSwarm never holds your funds — all capital stays in your broker account.
          </p>
        </div>

        {!loading && connections.length > 0 && (
          <section className="mb-8">
            <h2 className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-3">Connected</h2>
            <div className="space-y-3">
              {connections.map((conn) => (
                <ConnectionCard key={conn.id} conn={conn} onDelete={handleDeleted} />
              ))}
            </div>
          </section>
        )}

        {loading && <div className="flex items-center justify-center py-16 text-zinc-400 text-sm">Loading connections…</div>}

        {!loading && (
          <section>
            <h2 className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-3">
              {alpacaConnected ? 'Update / Add Connection' : 'Add Connection'}
            </h2>
            <div className="space-y-3">
              <AddAlpacaForm onAdded={handleAdded} />
              <AddZerodhaForm onAdded={handleAdded} existing={zerodhaConnected} />
              <UpstoxOAuthButton onAdded={handleAdded} />
              <AngelOneForm onAdded={handleAdded} />
            </div>
          </section>
        )}

        <div className="mt-10 flex items-start gap-3 px-5 py-4 rounded-2xl bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-200/60 dark:border-zinc-700/40">
          <div className="w-1.5 h-1.5 rounded-full bg-violet-500 mt-2 flex-shrink-0" />
          <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed">
            Your API keys and OAuth tokens are encrypted with AES-256 (Fernet) before storage. OAuth tokens are refreshed automatically on 401 — you only need to re-login if the refresh token expires too.
          </p>
        </div>
      </div>
    </AppShell>
  )
}

'use client'
import { useEffect, useState } from 'react'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import type { BillingCurrency, Subscription } from '@/lib/types'
import { CreditCard, Check, Globe, IndianRupee, ShieldCheck, ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'

// ── Region metadata ───────────────────────────────────────────────────────────
// Currency selects the payment gateway server-side: USD → Stripe, INR → Razorpay.
const REGIONS: {
  currency: BillingCurrency
  label: string
  sub: string
  price: string
  gateway: string
  icon: typeof Globe
}[] = [
  {
    currency: 'USD',
    label: 'Global',
    sub: 'Cards, Apple/Google Pay',
    price: '$49',
    gateway: 'Stripe',
    icon: Globe,
  },
  {
    currency: 'INR',
    label: 'India',
    sub: 'UPI AutoPay, cards, netbanking',
    price: '₹3,999',
    gateway: 'Razorpay',
    icon: IndianRupee,
  },
]

const QUANT_FEATURES = [
  'Deploy live trading agents on NSE/BSE & US markets',
  'Unlimited backtests & paper trading',
  'AI strategy co-pilot + rebalance approvals',
  'Priority execution queue',
]

function StatusBadge({ sub }: { sub: Subscription }) {
  const active = sub.is_active
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold',
        active
          ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400'
          : 'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400',
      )}
    >
      {active ? <ShieldCheck className="w-3.5 h-3.5" /> : null}
      {active ? 'Quant Tier active' : `Status: ${sub.subscription_status}`}
    </span>
  )
}

export default function BillingPage() {
  const [sub, setSub] = useState<Subscription | null>(null)
  const [loading, setLoading] = useState(true)
  const [currency, setCurrency] = useState<BillingCurrency>('USD')
  const [checkingOut, setCheckingOut] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .getSubscription()
      .then(setSub)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  async function handleCheckout() {
    setCheckingOut(true)
    setError(null)
    try {
      const res = await api.createCheckout(currency)
      // Redirect to the gateway's hosted checkout / authorization page.
      window.location.href = res.checkout_url
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Checkout failed')
      setCheckingOut(false)
    }
  }

  const isActive = sub?.is_active ?? false

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto animate-slide-up relative z-10 pb-20">
        <div className="mb-10 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-extrabold text-zinc-900 dark:text-zinc-100 tracking-tight">
              Billing
            </h1>
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
              The <span className="font-semibold">Quant Tier</span> unlocks live agent
              deployment. Pick your region — we route you to the right payment method.
            </p>
          </div>
          {sub && !loading && <StatusBadge sub={sub} />}
        </div>

        {loading && (
          <div className="flex items-center justify-center py-16 text-zinc-400 text-sm">Loading…</div>
        )}

        {!loading && (
          <GlassCard padding="none" className="overflow-hidden">
            <div className="px-6 py-5 border-b border-zinc-200/60 dark:border-zinc-700/40 flex items-center gap-3">
              <div className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center text-white bg-gradient-to-br from-violet-500 to-purple-600">
                <CreditCard className="w-5 h-5" />
              </div>
              <div>
                <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100">Quant Tier</p>
                <p className="text-xs text-zinc-400">Billed per month · cancel anytime</p>
              </div>
            </div>

            <div className="px-6 py-5 space-y-2">
              {QUANT_FEATURES.map((f) => (
                <div key={f} className="flex items-center gap-2.5 text-sm text-zinc-700 dark:text-zinc-300">
                  <Check className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                  {f}
                </div>
              ))}
            </div>

            {isActive ? (
              <div className="px-6 py-5 border-t border-zinc-200/60 dark:border-zinc-700/40">
                <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 text-sm font-medium">
                  <ShieldCheck className="w-4 h-4" />
                  You&apos;re on the Quant Tier — live deployment is unlocked.
                  {sub?.current_period_end && (
                    <span className="text-emerald-600/70 dark:text-emerald-500/70">
                      Renews {new Date(sub.current_period_end).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <div className="px-6 py-5 border-t border-zinc-200/60 dark:border-zinc-700/40">
                {/* ── Region selector ───────────────────────────────── */}
                <p className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-3">
                  Select your region
                </p>
                <div className="grid grid-cols-2 gap-3 mb-5">
                  {REGIONS.map((r) => {
                    const selected = currency === r.currency
                    const Icon = r.icon
                    return (
                      <button
                        key={r.currency}
                        type="button"
                        onClick={() => setCurrency(r.currency)}
                        className={cn(
                          'text-left px-4 py-4 rounded-2xl border transition-all',
                          selected
                            ? 'border-violet-400 dark:border-violet-500/60 bg-violet-50/60 dark:bg-violet-500/10 ring-2 ring-violet-500/20'
                            : 'border-zinc-200/70 dark:border-zinc-700/50 hover:border-violet-300 dark:hover:border-violet-500/40',
                        )}
                      >
                        <div className="flex items-center justify-between">
                          <Icon className="w-5 h-5 text-violet-500" />
                          {selected && <Check className="w-4 h-4 text-violet-500" />}
                        </div>
                        <p className="mt-2 text-sm font-bold text-zinc-900 dark:text-zinc-100">
                          {r.label}{' '}
                          <span className="text-zinc-400 font-medium">/ {r.currency}</span>
                        </p>
                        <p className="text-[11px] text-zinc-400 mt-0.5">{r.sub}</p>
                        <p className="mt-2 text-sm font-semibold text-zinc-700 dark:text-zinc-200">
                          {r.price}
                          <span className="text-xs font-normal text-zinc-400">/mo</span>
                        </p>
                        <p className="mt-1 text-[10px] text-zinc-400 flex items-center gap-1">
                          via {r.gateway}
                        </p>
                      </button>
                    )
                  })}
                </div>

                {error && (
                  <p className="mb-3 text-xs text-rose-500 dark:text-rose-400">{error}</p>
                )}

                <Button
                  onClick={handleCheckout}
                  loading={checkingOut}
                  size="lg"
                  className="w-full"
                >
                  {!checkingOut && <ExternalLink className="w-4 h-4" />}
                  Upgrade to Quant Tier
                </Button>
                <p className="mt-3 text-[11px] text-center text-zinc-400">
                  You&apos;ll be redirected to {currency === 'INR' ? 'Razorpay' : 'Stripe'} to
                  complete payment securely.
                </p>
              </div>
            )}
          </GlassCard>
        )}

        <div className="mt-8 flex items-start gap-3 px-5 py-4 rounded-2xl bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-200/60 dark:border-zinc-700/40">
          <ShieldCheck className="w-4 h-4 text-violet-500 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed">
            Payments are processed by Stripe (Global) or Razorpay (India). AlphaSwarm never
            stores your card or UPI details. Paper trading and backtesting are always free —
            you only need the Quant Tier to deploy live agents.
          </p>
        </div>
      </div>
    </AppShell>
  )
}

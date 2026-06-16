'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Target, GraduationCap, Shield, TrendingUp, DollarSign, ArrowRight, ArrowLeft, Zap } from 'lucide-react'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

type Goal = 'retirement' | 'education' | 'emergency' | 'wealth' | 'income'
type Risk = 'conservative' | 'moderate' | 'aggressive'
type Horizon = 'lt1' | '1to3' | '3to5' | '5to10' | 'gt10'

const GOALS: { id: Goal; icon: typeof Target; label: string; desc: string }[] = [
  { id: 'retirement',  icon: Target,      label: 'Retirement',           desc: 'Long-term wealth for life after work' },
  { id: 'education',   icon: GraduationCap, label: 'Child Education',      desc: 'Corpus for future tuition & costs' },
  { id: 'emergency',   icon: Shield,      label: 'Emergency Fund',        desc: 'Liquid buffer for unexpected events' },
  { id: 'wealth',      icon: TrendingUp,  label: 'Wealth Building',       desc: 'Grow capital over time' },
  { id: 'income',      icon: DollarSign,  label: 'Regular Income',        desc: 'Dividend or coupon-based cash flow' },
]

const RISKS: { id: Risk; label: string; desc: string; color: string }[] = [
  { id: 'conservative', label: 'Conservative', desc: 'Capital preservation over growth',    color: 'border-emerald-400 bg-emerald-50/40 dark:bg-emerald-500/10' },
  { id: 'moderate',     label: 'Moderate',     desc: 'Balanced growth with managed risk',   color: 'border-violet-400 bg-violet-50/40 dark:bg-violet-500/10' },
  { id: 'aggressive',   label: 'Aggressive',   desc: 'Maximum growth, higher volatility',   color: 'border-rose-400 bg-rose-50/40 dark:bg-rose-500/10' },
]

const HORIZONS: { id: Horizon; label: string }[] = [
  { id: 'lt1',   label: '< 1 year' },
  { id: '1to3',  label: '1 – 3 years' },
  { id: '3to5',  label: '3 – 5 years' },
  { id: '5to10', label: '5 – 10 years' },
  { id: 'gt10',  label: '10+ years' },
]

function suggestedPrompt(goal: Goal, risk: Risk, horizon: Horizon): string {
  const horizonMap: Record<Horizon, string> = {
    lt1:   'short-term (< 1 year)',
    '1to3': '1 to 3 year',
    '3to5': '3 to 5 year',
    '5to10': '5 to 10 year',
    gt10:  'long-term (10+ year)',
  }
  const riskMap: Record<Risk, string> = {
    conservative: 'low-risk, capital-preserving',
    moderate:     'balanced, moderate-risk',
    aggressive:   'high-growth, higher-risk',
  }
  const goalMap: Record<Goal, string> = {
    retirement: 'build a retirement corpus',
    education:  'save for child education expenses',
    emergency:  'maintain a liquid emergency fund via short-duration instruments',
    wealth:     'grow wealth over time through diversified equity',
    income:     'generate regular income through dividends and coupons',
  }
  return `Create a ${riskMap[risk]} strategy to ${goalMap[goal]} over a ${horizonMap[horizon]} horizon.`
}

interface Props {
  onBuild: () => void
}

export function GoalWizard({ onBuild }: Props) {
  const router = useRouter()
  const [step, setStep]       = useState<0 | 1 | 2>(0)
  const [goal, setGoal]       = useState<Goal | null>(null)
  const [risk, setRisk]       = useState<Risk | null>(null)
  const [horizon, setHorizon] = useState<Horizon | null>(null)

  function handleFinish() {
    if (!goal || !risk || !horizon) return
    const prompt = encodeURIComponent(suggestedPrompt(goal, risk, horizon))
    router.push(`/strategies/new?prompt=${prompt}`)
  }

  return (
    <div className={cn(
      'relative overflow-hidden rounded-2xl',
      'border border-zinc-200 dark:border-white/[0.07]',
      'bg-white dark:bg-zinc-900/40',
    )}>
      {/* Ambient glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[60%] h-48
          bg-gradient-to-b from-violet-500/08 dark:from-violet-500/15 to-transparent rounded-full blur-3xl" />
      </div>

      <div className="relative z-10 px-8 py-10 max-w-2xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl mx-auto mb-5
            bg-gradient-to-br from-violet-500 to-violet-700
            flex items-center justify-center
            shadow-[0_8px_32px_rgba(124,58,237,0.35)]">
            <Zap className="w-7 h-7 text-white fill-white/20" />
          </div>
          <h2 className="text-2xl font-extrabold text-zinc-900 dark:text-zinc-50 mb-1.5 tracking-tight">
            What's your investing goal?
          </h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Answer 3 quick questions — AlphaSwarm will build a personalised AI strategy for you.
          </p>
        </div>

        {/* Step dots */}
        <div className="flex justify-center gap-2 mb-8">
          {[0, 1, 2].map((s) => (
            <div key={s} className={cn(
              'h-1.5 rounded-full transition-all duration-300',
              s === step ? 'w-8 bg-violet-500' : s < step ? 'w-4 bg-violet-300 dark:bg-violet-700' : 'w-4 bg-zinc-200 dark:bg-zinc-700',
            )} />
          ))}
        </div>

        {/* Step 0: Goal */}
        {step === 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {GOALS.map((g) => (
              <button
                key={g.id}
                onClick={() => { setGoal(g.id); setStep(1) }}
                className={cn(
                  'flex items-center gap-3 px-4 py-4 rounded-xl text-left transition-all duration-150',
                  'border-2 hover:scale-[1.02]',
                  goal === g.id
                    ? 'border-violet-500 bg-violet-50 dark:bg-violet-500/15 shadow-[0_0_0_3px_rgba(124,58,237,0.15)]'
                    : 'border-zinc-200 dark:border-zinc-700 hover:border-violet-300 dark:hover:border-violet-600',
                )}
              >
                <div className={cn(
                  'w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0',
                  goal === g.id
                    ? 'bg-violet-500 text-white'
                    : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400',
                )}>
                  <g.icon className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{g.label}</p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 truncate">{g.desc}</p>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Step 1: Risk */}
        {step === 1 && (
          <div className="space-y-3">
            {RISKS.map((r) => (
              <button
                key={r.id}
                onClick={() => { setRisk(r.id); setStep(2) }}
                className={cn(
                  'w-full flex items-center gap-4 px-5 py-4 rounded-xl text-left transition-all duration-150',
                  'border-2 hover:scale-[1.01]',
                  risk === r.id ? r.color + ' border-opacity-100' : 'border-zinc-200 dark:border-zinc-700 hover:border-zinc-300 dark:hover:border-zinc-600',
                )}
              >
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{r.label}</p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">{r.desc}</p>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Step 2: Horizon */}
        {step === 2 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
            {HORIZONS.map((h) => (
              <button
                key={h.id}
                onClick={() => setHorizon(h.id)}
                className={cn(
                  'py-3 px-4 rounded-xl text-sm font-semibold border-2 transition-all duration-150 hover:scale-[1.02]',
                  horizon === h.id
                    ? 'border-violet-500 bg-violet-50 dark:bg-violet-500/15 text-violet-700 dark:text-violet-300'
                    : 'border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 hover:border-violet-300 dark:hover:border-violet-600',
                )}
              >
                {h.label}
              </button>
            ))}
          </div>
        )}

        {/* Nav buttons */}
        <div className="flex items-center justify-between mt-8 gap-4">
          {step > 0 ? (
            <button
              onClick={() => setStep((s) => (s - 1) as 0 | 1 | 2)}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" /> Back
            </button>
          ) : (
            <button
              onClick={onBuild}
              className="text-sm font-medium text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors"
            >
              Skip wizard
            </button>
          )}

          {step === 2 && (
            <Button
              onClick={handleFinish}
              disabled={!horizon}
              className="shadow-[0_4px_20px_rgba(109,40,217,0.35)] hover:shadow-[0_6px_28px_rgba(109,40,217,0.5)]"
            >
              Build My Strategy
              <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

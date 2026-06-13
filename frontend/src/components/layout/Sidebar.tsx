'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import {
  LayoutDashboard, Zap, Activity, Settings, TrendingUp, ChevronRight, Brain, CandlestickChart,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { getUserProfile } from '@/lib/api'
import type { UserProfile } from '@/lib/types'

function formatPlan(plan: string): string {
  return plan
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

const NAV_SECTIONS = [
  {
    id: 'trading',
    label: 'Trading',
    items: [
      { href: '/',               icon: LayoutDashboard,   label: 'Dashboard'  },
      { href: '/terminal',       icon: CandlestickChart,  label: 'Terminal'   },
      { href: '/strategies/new', icon: Zap,               label: 'Strategies' },
      { href: '/runs',           icon: Activity,          label: 'Runs', soon: true },
    ],
  },
  {
    id: 'account',
    label: 'Account',
    items: [
      { href: '/settings/brokers', icon: Settings, label: 'Brokers' },
      { href: '/settings/ai',      icon: Brain,    label: 'AI Models' },
    ],
  },
]

/* ── Item ────────────────────────────────────────────────────────────────── */
function NavItem({
  href, icon: Icon, label, soon, active,
}: {
  href: string; icon: typeof Zap; label: string; soon?: boolean; active?: boolean
}) {
  if (soon) {
    return (
      <div className="relative flex items-center gap-3 px-4 py-2.5 text-sm
        text-zinc-400 dark:text-zinc-600 cursor-not-allowed select-none rounded-xl">
        <Icon className="w-[17px] h-[17px] flex-shrink-0" />
        <span className="flex-1 leading-none">{label}</span>
        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full border
          border-zinc-200 dark:border-zinc-800 text-zinc-400 dark:text-zinc-600
          tracking-wider uppercase">
          Soon
        </span>
      </div>
    )
  }

  return (
    <Link
      href={href}
      data-active={active ? 'true' : undefined}
      className={cn(
        'relative z-10 flex items-center gap-3 px-4 py-2.5 text-sm rounded-xl',
        'transition-colors duration-150 select-none',
        active
          ? 'text-white font-semibold'
          : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100',
      )}
    >
      <Icon className={cn(
        'w-[17px] h-[17px] flex-shrink-0 transition-transform duration-200',
        active ? 'scale-110' : '',
      )} />
      <span className="flex-1 leading-none">{label}</span>
      {active && <ChevronRight className="w-3.5 h-3.5 opacity-60 flex-shrink-0" />}
    </Link>
  )
}

/* ── Pill ────────────────────────────────────────────────────────────────── */
function LiquidPill({ top, height }: { top: number; height: number }) {
  return (
    <motion.div
      aria-hidden
      layout
      animate={{ top, height }}
      transition={{ type: 'spring', stiffness: 420, damping: 36, mass: 0.8 }}
      style={{
        position: 'absolute',
        insetInline: 0,
        borderRadius: 12,
        pointerEvents: 'none',
        zIndex: 0,
        overflow: 'hidden',
        /* Base — light mode: solid violet button feel */
        background: 'linear-gradient(135deg, #6D28D9 0%, #7C3AED 100%)',
        boxShadow: [
          '0 4px 20px rgba(109,40,217,0.40)',
          '0 0 0 1px rgba(109,40,217,0.35)',
          'inset 0 1px 0 rgba(255,255,255,0.22)',
        ].join(', '),
      }}
    >
      {/* Shimmer top highlight */}
      <div style={{
        position: 'absolute',
        top: 0, left: '12%', right: '12%', height: 1,
        background: 'linear-gradient(90deg,transparent,rgba(255,255,255,0.6),transparent)',
      }} />
      {/* Subtle inner glow */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'linear-gradient(180deg,rgba(255,255,255,0.09) 0%,transparent 55%)',
      }} />
      {/* Left accent bar — glowing white edge */}
      <div style={{
        position: 'absolute',
        left: 0, top: '18%', bottom: '18%', width: 3,
        borderRadius: '0 3px 3px 0',
        background: 'rgba(255,255,255,0.95)',
        boxShadow: '3px 0 14px rgba(255,255,255,0.7)',
      }} />
    </motion.div>
  )
}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
export function Sidebar() {
  const pathname = usePathname()
  const [profile, setProfile] = useState<UserProfile | null>(null)

  useEffect(() => {
    setProfile(getUserProfile())
  }, [])

  /* One container ref per section — pill is local to each group */
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const [pills, setPills] = useState<Record<string, { top: number; height: number } | null>>({})

  const measure = useCallback(() => {
    const next: Record<string, { top: number; height: number } | null> = {}
    for (const section of NAV_SECTIONS) {
      const container = sectionRefs.current[section.id]
      if (!container) { next[section.id] = null; continue }
      const active = container.querySelector<HTMLElement>('[data-active="true"]')
      if (!active) { next[section.id] = null; continue }
      const cr = container.getBoundingClientRect()
      const ar = active.getBoundingClientRect()
      next[section.id] = {
        top:    ar.top - cr.top,
        height: ar.height,
      }
    }
    setPills(next)
  }, [])

  useEffect(() => {
    /* rAF lets the DOM settle after navigation before measuring */
    const id = requestAnimationFrame(measure)
    return () => cancelAnimationFrame(id)
  }, [pathname, measure])

  function isActive(href: string) {
    if (href === '/') return pathname === '/'
    return pathname === href || pathname.startsWith(href + '/')
  }

  return (
    <aside className="fixed inset-y-0 left-0 w-[240px] flex flex-col glass-sidebar z-30">

      {/* ── Logo ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-5 h-[62px]
        border-b border-black/[0.07] dark:border-white/[0.05]">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg flex-shrink-0
          bg-gradient-to-br from-violet-500 to-violet-700
          shadow-[0_2px_14px_rgba(124,58,237,0.5)]">
          <TrendingUp className="w-4 h-4 text-white" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-bold text-zinc-900 dark:text-zinc-50 leading-none tracking-tight">
            AlphaSwarm
          </p>
          <div className="flex items-center gap-1.5 mt-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500
              shadow-[0_0_5px_rgba(16,185,129,0.8)]" />
            <p className="text-[10px] font-medium text-zinc-400 dark:text-zinc-500 leading-none">
              Paper Mode
            </p>
          </div>
        </div>
      </div>

      {/* ── Navigation ───────────────────────────────────────────── */}
      <nav className="flex-1 py-4 overflow-y-auto" style={{ scrollbarWidth: 'none' as const }}>
        <div className="px-3 space-y-5">
          {NAV_SECTIONS.map((section) => {
            const pill = pills[section.id]
            const hasPill = pill !== null && pill !== undefined

            return (
              <div key={section.id}>
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] px-4 pb-2
                  text-zinc-400 dark:text-zinc-600">
                  {section.label}
                </p>

                {/* Items + floating pill */}
                <div
                  className="relative"
                  ref={(el) => { sectionRefs.current[section.id] = el }}
                >
                  {hasPill && <LiquidPill top={pill.top} height={pill.height} />}

                  <div className="space-y-0.5">
                    {section.items.map((item) => (
                      <NavItem
                        key={item.href}
                        {...item}
                        active={!item.soon && isActive(item.href)}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </nav>

      {/* ── User footer ──────────────────────────────────────────── */}
      <div className="px-3 pb-3 pt-2 border-t border-black/[0.07] dark:border-white/[0.05]">
        <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl cursor-pointer group
          hover:bg-zinc-100 dark:hover:bg-white/[0.05] transition-colors">
          <div className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center
            bg-gradient-to-br from-violet-400 to-violet-600
            text-[11px] font-bold text-white
            shadow-[0_2px_10px_rgba(124,58,237,0.35)]
            group-hover:shadow-[0_2px_16px_rgba(124,58,237,0.55)]
            transition-shadow">
            {profile?.display_name ? profile.display_name.charAt(0).toUpperCase() : '?'}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-zinc-800 dark:text-zinc-200 truncate leading-none">
              {profile?.display_name ?? 'Loading…'}
            </p>
            <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mt-0.5 leading-none">
              {profile?.plan ? formatPlan(profile.plan) : profile?.tenant_name ?? ''}
            </p>
          </div>
        </div>
      </div>

    </aside>
  )
}

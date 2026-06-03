'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, Zap, Activity, Settings, TrendingUp, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

const NAV_SECTIONS = [
  {
    label: 'Trading',
    items: [
      { href: '/',               icon: LayoutDashboard, label: 'Dashboard'  },
      { href: '/strategies/new', icon: Zap,             label: 'Strategies' },
      { href: '/runs',           icon: Activity,        label: 'Runs', soon: true },
    ],
  },
  {
    label: 'Account',
    items: [
      { href: '/settings/brokers', icon: Settings, label: 'Settings' },
    ],
  },
]

function NavItem({ href, icon: Icon, label, soon }: {
  href: string; icon: typeof Zap; label: string; soon?: boolean
}) {
  const path = usePathname()
  const active = path === href || (href !== '/' && path.startsWith(href.replace('/new', '')))

  if (soon) {
    return (
      <div className="flex items-center gap-3 px-4 py-2.5 text-sm text-zinc-400 dark:text-zinc-600 cursor-not-allowed select-none">
        <Icon className="w-[17px] h-[17px] flex-shrink-0" />
        <span className="flex-1">{label}</span>
        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full border border-zinc-200 dark:border-zinc-800 text-zinc-400 dark:text-zinc-600 tracking-wider uppercase">
          Soon
        </span>
      </div>
    )
  }

  return (
    <Link
      href={href}
      className={cn(
        'group flex items-center gap-3 px-4 py-2.5 text-sm transition-all duration-150 select-none relative',
        active
          ? [
              'rounded-xl font-semibold',
              'bg-violet-50 text-violet-700',
              'dark:bg-violet-500/12 dark:text-violet-300',
              // Glow ring visible in dark
              'dark:shadow-[inset_0_0_0_1px_rgba(139,92,246,0.20)]',
            ]
          : [
              'rounded-xl',
              'text-zinc-600 dark:text-zinc-400',
              'hover:bg-zinc-100 dark:hover:bg-white/[0.05]',
              'hover:text-zinc-900 dark:hover:text-zinc-100',
            ],
      )}
    >
      {/* Active left bar */}
      {active && (
        <span
          aria-hidden
          className={cn(
            'absolute left-0 top-[6px] bottom-[6px] w-[3px] rounded-r-full',
            'bg-violet-600 dark:bg-violet-400',
            'shadow-[2px_0_10px_rgba(124,58,237,0.55)] dark:shadow-[2px_0_12px_rgba(139,92,246,0.7)]',
          )}
        />
      )}

      <Icon className={cn('w-[17px] h-[17px] flex-shrink-0 transition-transform duration-150', active ? 'scale-110' : 'group-hover:scale-105')} />
      <span className="flex-1 leading-none">{label}</span>
      {active && <ChevronRight className="w-3.5 h-3.5 opacity-40 flex-shrink-0" />}
    </Link>
  )
}

export function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 w-[240px] flex flex-col glass-sidebar z-30">

      {/* ── Logo ──────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-5 h-[62px] border-b border-black/[0.07] dark:border-white/[0.05]">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg flex-shrink-0
          bg-gradient-to-br from-violet-500 to-violet-700
          shadow-[0_2px_14px_rgba(124,58,237,0.45)]">
          <TrendingUp className="w-4 h-4 text-white" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-bold text-zinc-900 dark:text-zinc-50 leading-none tracking-tight">AlphaSwarm</p>
          <div className="flex items-center gap-1.5 mt-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_5px_rgba(16,185,129,0.7)]" />
            <p className="text-[10px] font-medium text-zinc-400 dark:text-zinc-500 leading-none">Paper Mode</p>
          </div>
        </div>
      </div>

      {/* ── Nav sections ─────────────────────────────────────────────── */}
      <nav className="flex-1 py-3 overflow-y-auto" style={{ overflowX: 'visible' }}>
        <div className="space-y-4 px-2">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label}>
              <p className="text-[10px] font-bold text-zinc-400 dark:text-zinc-600 uppercase tracking-[0.12em] px-4 pb-1">
                {section.label}
              </p>
              <div className="space-y-0.5">
                {section.items.map((item) => <NavItem key={item.href} {...item} />)}
              </div>
            </div>
          ))}
        </div>
      </nav>

      {/* ── User footer ──────────────────────────────────────────────── */}
      <div className="px-3 pb-3 pt-2 border-t border-black/[0.07] dark:border-white/[0.05]">
        <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl
          hover:bg-zinc-100 dark:hover:bg-white/[0.05]
          transition-colors cursor-pointer group">
          <div className="w-8 h-8 rounded-full flex-shrink-0
            bg-gradient-to-br from-violet-400 to-violet-600
            flex items-center justify-center
            text-[11px] font-bold text-white
            shadow-[0_2px_10px_rgba(124,58,237,0.35)]
            group-hover:shadow-[0_2px_14px_rgba(124,58,237,0.5)]
            transition-shadow">
            A
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-zinc-800 dark:text-zinc-200 truncate leading-none">
              Ankit Singh
            </p>
            <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mt-0.5 leading-none">
              Starter Plan
            </p>
          </div>
        </div>
      </div>

    </aside>
  )
}

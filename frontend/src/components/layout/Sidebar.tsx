'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, Zap, Activity, Settings, TrendingUp } from 'lucide-react'
import { cn } from '@/lib/utils'

const nav = [
  { href: '/',            icon: LayoutDashboard, label: 'Dashboard' },
  { href: '/strategies/new',  icon: Zap,             label: 'Strategies' },
  { href: '/runs',        icon: Activity,         label: 'Runs',     soon: true },
]

const bottom = [
  { href: '/settings/brokers', icon: Settings, label: 'Settings' },
]

function NavLink({ href, icon: Icon, label, soon }: {
  href: string; icon: typeof Zap; label: string; soon?: boolean
}) {
  const path = usePathname()
  const active = path === href || (href !== '/' && path.startsWith(href))

  if (soon) {
    return (
      <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-zinc-400 dark:text-zinc-600">
        <Icon className="w-[18px] h-[18px] flex-shrink-0" />
        <span className="text-sm">{label}</span>
        <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-400">Soon</span>
      </div>
    )
  }

  return (
    <Link
      href={href}
      className={cn(
        'flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-150 text-sm',
        active
          ? 'bg-violet-50 text-violet-700 dark:bg-violet-500/10 dark:text-violet-400 font-medium'
          : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800/70 hover:text-zinc-900 dark:hover:text-zinc-100',
      )}
    >
      <Icon className="w-[18px] h-[18px] flex-shrink-0" />
      {label}
    </Link>
  )
}

export function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 w-[230px] flex flex-col glass-sidebar z-30">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 h-[60px] border-b border-black/[0.07] dark:border-white/[0.07]">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-violet-700 shadow-sm shadow-violet-500/30 flex-shrink-0">
          <TrendingUp className="w-4 h-4 text-white" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 leading-none">AlphaSwarm</p>
          <p className="text-[10px] text-zinc-400 mt-0.5 leading-none">Paper Trading</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
        {nav.map((item) => <NavLink key={item.href} {...item} />)}
      </nav>

      {/* Bottom */}
      <div className="px-3 py-3 border-t border-black/[0.07] dark:border-white/[0.07] space-y-0.5">
        {bottom.map((item) => <NavLink key={item.href} {...item} />)}
        <div className="flex items-center gap-2.5 px-3 py-2 mt-1">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-violet-400 to-violet-600 flex items-center justify-center flex-shrink-0 text-[11px] font-bold text-white">
            A
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-zinc-700 dark:text-zinc-300 truncate leading-none">Ankit Singh</p>
            <p className="text-[10px] text-zinc-400 mt-0.5 leading-none">Starter Plan</p>
          </div>
        </div>
      </div>
    </aside>
  )
}

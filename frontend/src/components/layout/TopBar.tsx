'use client'
import { usePathname, useRouter } from 'next/navigation'
import { ThemeToggle } from '@/components/ui/ThemeToggle'
import { useEffect, useState } from 'react'
import { api, clearTokens, getRefreshToken } from '@/lib/api'
import { LogOut, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

const BREADCRUMBS: Record<string, string[]> = {
  '/':                  ['Dashboard'],
  '/strategies/new':    ['Strategies', 'New'],
  '/settings/brokers':  ['Settings', 'Brokers'],
}

function ApiBadge() {
  const [state, setState] = useState<'checking' | 'online' | 'offline'>('checking')

  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/health`, {
          signal: AbortSignal.timeout(3000),
        })
        setState(r.ok ? 'online' : 'offline')
      } catch { setState('offline') }
    }
    check()
    const id = setInterval(check, 30_000)
    return () => clearInterval(id)
  }, [])

  const dot = {
    online:   'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.7)]',
    offline:  'bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.7)]',
    checking: 'bg-zinc-400 animate-pulse',
  }[state]

  const label = { online: 'Live', offline: 'Offline', checking: '…' }[state]

  return (
    <div className={cn(
      'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium',
      'border transition-colors',
      state === 'online'
        ? 'border-emerald-500/25 bg-emerald-500/08 text-emerald-600 dark:text-emerald-400'
        : state === 'offline'
          ? 'border-rose-500/25 bg-rose-500/08 text-rose-600 dark:text-rose-400'
          : 'border-zinc-300/40 dark:border-zinc-700/40 text-zinc-500',
    )}>
      <span className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', dot)} />
      API {label}
    </div>
  )
}

export function TopBar() {
  const path = usePathname()
  const router = useRouter()
  const crumbs = BREADCRUMBS[path] ?? (path.startsWith('/strategies/') ? ['Strategies', 'Detail'] : [path.slice(1)])

  async function handleLogout() {
    const refresh = getRefreshToken()
    if (refresh) {
      try { await api.logout(refresh) } catch { /* ignore */ }
    }
    clearTokens()
    router.replace('/login')
  }

  return (
    <header className="fixed top-0 left-[240px] right-0 h-[62px] z-20 glass-topbar flex items-center px-6 gap-4">

      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 flex-1 min-w-0">
        {crumbs.map((crumb, i) => (
          <span key={crumb} className="flex items-center gap-1.5">
            {i > 0 && <ChevronRight className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-600 flex-shrink-0" />}
            <span className={cn(
              'text-sm leading-none truncate',
              i === crumbs.length - 1
                ? 'font-semibold text-zinc-900 dark:text-zinc-100'
                : 'font-medium text-zinc-400 dark:text-zinc-600',
            )}>
              {crumb}
            </span>
          </span>
        ))}
      </div>

      {/* Right controls */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <ApiBadge />
        <ThemeToggle />
        <div className="w-px h-4 bg-zinc-200 dark:bg-zinc-800" />
        <button
          onClick={handleLogout}
          title="Sign out"
          className="flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400
            hover:text-rose-600 dark:hover:text-rose-400
            transition-colors px-2 py-1.5 rounded-lg
            hover:bg-rose-50 dark:hover:bg-rose-500/08"
        >
          <LogOut className="w-3.5 h-3.5" />
          <span className="hidden sm:inline font-medium">Sign out</span>
        </button>
      </div>
    </header>
  )
}

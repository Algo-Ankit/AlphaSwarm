'use client'
import { usePathname } from 'next/navigation'
import { ThemeToggle } from '@/components/ui/ThemeToggle'
import { useEffect, useState } from 'react'

const titles: Record<string, string> = {
  '/':                  'Dashboard',
  '/strategies':        'Strategies',
  '/strategies/new':    'New Strategy',
}

function ApiPill() {
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

  const color = state === 'online' ? 'bg-emerald-500' : state === 'offline' ? 'bg-rose-500' : 'bg-zinc-300 dark:bg-zinc-600'
  const label = state === 'online' ? 'API Online' : state === 'offline' ? 'API Offline' : 'Connecting'

  return (
    <div className="flex items-center gap-1.5 text-[11px] text-zinc-500 dark:text-zinc-400">
      <span className={`w-1.5 h-1.5 rounded-full ${color} ${state === 'online' ? '' : ''}`} />
      {label}
    </div>
  )
}

export function TopBar() {
  const path = usePathname()
  const title = titles[path] ?? (path.startsWith('/strategies/') ? 'Strategy' : path)

  return (
    <header className="fixed top-0 left-[230px] right-0 h-[60px] z-20 glass-topbar flex items-center px-6 gap-4">
      <h1 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 flex-1">{title}</h1>
      <ApiPill />
      <ThemeToggle />
    </header>
  )
}

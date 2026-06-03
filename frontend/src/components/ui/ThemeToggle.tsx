'use client'
import { useTheme } from 'next-themes'
import { Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  if (!mounted) return <div className={cn('w-[34px] h-[34px]', className)} />

  const isDark = theme === 'dark'

  return (
    <button
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className={cn(
        'relative flex items-center justify-center w-[34px] h-[34px] rounded-xl',
        'transition-all duration-200 select-none',
        isDark
          ? 'bg-zinc-800 text-amber-400 hover:bg-zinc-700 hover:text-amber-300 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]'
          : 'bg-zinc-100 text-violet-600 hover:bg-violet-50 hover:text-violet-700 shadow-[inset_0_0_0_1px_rgba(0,0,0,0.07)]',
        className,
      )}
    >
      {isDark
        ? <Sun  className="w-[15px] h-[15px]" />
        : <Moon className="w-[15px] h-[15px]" />}
    </button>
  )
}

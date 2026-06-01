'use client'
import { useTheme } from 'next-themes'
import { Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  if (!mounted) return <div className={cn('w-9 h-9', className)} />

  return (
    <button
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      aria-label="Toggle theme"
      className={cn(
        'flex items-center justify-center w-9 h-9 rounded-xl',
        'text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100',
        'hover:bg-zinc-100 dark:hover:bg-zinc-800',
        'transition-all duration-200',
        className,
      )}
    >
      {theme === 'dark'
        ? <Sun className="w-[18px] h-[18px]" />
        : <Moon className="w-[18px] h-[18px]" />}
    </button>
  )
}

import { cn } from '@/lib/utils'

type Variant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'muted'

const variants: Record<Variant, string> = {
  default: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
  success: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400',
  warning: 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400',
  danger:  'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400',
  info:    'bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400',
  muted:   'bg-zinc-50 text-zinc-400 dark:bg-zinc-900 dark:text-zinc-500',
}

const dots: Record<Variant, string> = {
  default: 'bg-zinc-400',
  success: 'bg-emerald-500',
  warning: 'bg-amber-500',
  danger:  'bg-rose-500',
  info:    'bg-blue-500',
  muted:   'bg-zinc-400',
}

interface BadgeProps {
  children: React.ReactNode
  variant?: Variant
  dot?: boolean
  pulse?: boolean
  className?: string
}

export function Badge({ children, variant = 'default', dot, pulse, className }: BadgeProps) {
  return (
    <span className={cn(
      'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium',
      variants[variant],
      className,
    )}>
      {dot && (
        <span className={cn('inline-block w-1.5 h-1.5 rounded-full flex-shrink-0', dots[variant], pulse && 'animate-pulse')} />
      )}
      {children}
    </span>
  )
}

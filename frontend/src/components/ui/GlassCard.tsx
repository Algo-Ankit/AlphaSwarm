import { cn } from '@/lib/utils'
import { type HTMLAttributes } from 'react'

type Padding = 'none' | 'sm' | 'md' | 'lg'

const paddings: Record<Padding, string> = {
  none: '',
  sm:   'p-4',
  md:   'p-6',
  lg:   'p-8',
}

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  padding?: Padding
  hover?: boolean
  glow?: boolean
}

export function GlassCard({ className, padding = 'md', hover, glow, children, ...props }: GlassCardProps) {
  return (
    <div
      className={cn(
        'glass-card',
        paddings[padding],
        hover && [
          'cursor-pointer transition-all duration-200',
          'hover:-translate-y-0.5 hover:shadow-lg',
          'hover:border-zinc-200/80 dark:hover:border-zinc-600/40',
        ],
        glow && 'ring-1 ring-violet-400/20 dark:ring-violet-500/20',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}

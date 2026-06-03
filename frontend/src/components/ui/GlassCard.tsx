import { cn } from '@/lib/utils'
import { type HTMLAttributes } from 'react'

type Padding = 'none' | 'sm' | 'md' | 'lg'

const paddings: Record<Padding, string> = {
  none: '',
  sm:   'p-4',
  md:   'p-5',
  lg:   'p-7',
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
        hover && 'cursor-pointer',
        glow && [
          'ring-1 ring-violet-400/20 dark:ring-violet-500/20',
          'shadow-[0_0_0_1px_rgba(109,40,217,0.15),0_8px_28px_rgba(0,0,0,0.08)]',
          'dark:shadow-[0_0_0_1px_rgba(139,92,246,0.25),0_8px_32px_rgba(0,0,0,0.5)]',
        ],
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}

import { cn } from '@/lib/utils'

/**
 * Displays a data quality score with a small colored bar.
 * 80+ = forest green, 50-79 = copper, <50 = warm stone.
 */
export function QualityIndicator({ score, className }) {
  if (score == null) {
    return <span className="text-muted-foreground">--</span>
  }

  const pct = Math.min(100, Math.max(0, score))
  const color =
    score >= 80 ? 'bg-[#3a7d44]' :
    score >= 50 ? 'bg-[#c78c4e]' :
    'bg-[#d9cebb]'

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <span className="text-sm font-medium tabular-nums w-7 text-right">{score}</span>
      <div className="h-2 w-16 bg-muted rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', color)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
